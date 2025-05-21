from odoo.exceptions import UserError
import requests
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class WhatsAppTemplate(models.Model):
    _name = 'whatsapp.template'
    _description = 'WhatsApp Message Template'
    _rec_name = 'name'

    name = fields.Char(string="Template Name", required=True)
    template_id = fields.Char(string="Template ID", help="Meta Template ID")
    lang = fields.Many2one(
        'res.lang',
        string="Language",
        required=True,
        default=lambda self: self.env['res.lang'].search([('code', '=', 'en_US')], limit=1),
        help="Language of the template (e.g., English (US))"
    )
    category = fields.Selection(
        [
            ('AUTHENTICATION', 'Authentication'),
            ('MARKETING', 'Marketing'),
            ('UTILITY', 'Utility'),
        ],
        string="Category",
        help="Template category (e.g., AUTHENTICATION, MARKETING, UTILITY)"
    )
    status = fields.Selection([
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PAUSED', 'Paused'),
    ], string="Status", help="Template approval status")
    add_status = fields.Selection([
        ('new', 'New'),
        ('added', 'Added'),
    ], string="New Temp Status", default='new')
    parameter_format = fields.Selection([
        ('POSITIONAL', 'Positional'),
        ('STRUCTURED', 'Structured'),
    ], string="Parameter Format", default='POSITIONAL', help="Format for template parameters")
    component_ids = fields.One2many(
        'whatsapp.template.component',
        'template_id',
        string="Components",
        help="Components of the template (e.g., HEADER, BODY, FOOTER, BUTTONS)"
    )
    config_id = fields.Many2one(
        'whatsapp.config',
        string="WhatsApp Configuration",
        required=True,
        help="Linked WhatsApp configuration"
    )
    available = fields.Many2one(
        'ir.model',
        string="Available In",
        help="Odoo model where this template can be used (e.g., Sale Order)"
    )
    message = fields.Text(
        string="Message",
        help="The main message content from the BODY component of the template",
        compute='_compute_message',
        inverse='_inverse_message',
        store=True,  # Store the computed value in the database
        readonly=False,  # Allow editing in the UI
    )

    @api.depends('component_ids', 'component_ids.text')
    def _compute_message(self):
        """Compute the message field from the BODY component's text."""
        for record in self:
            body_component = record.component_ids.filtered(lambda c: c.type == 'BODY')
            record.message = body_component.text if body_component else False

    def _inverse_message(self):
        """Update the BODY component's text when the message field is set."""
        for record in self:
            body_component = record.component_ids.filtered(lambda c: c.type == 'BODY')
            if record.message:
                if body_component:
                    body_component.text = record.message
                else:
                    record.component_ids = [(0, 0, {
                        'type': 'BODY',
                        'text': record.message,
                    })]
            else:
                if body_component:
                    body_component.unlink()

    def action_create_template(self):
        """Create a new template on Meta."""
        self.ensure_one()
        try:
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
                'Content-Type': 'application/json',
            }

            components = []
            for component in self.component_ids:
                comp_data = {
                    'type': component.type,
                }
                if component.type != 'BUTTONS' and component.text:
                    comp_data['text'] = component.text

                if component.type == 'HEADER' and component.format:
                    comp_data['format'] = component.format
                if component.parameter_ids:
                    if component.type in ['HEADER', 'BODY']:
                        examples = {}
                        if self.parameter_format == 'POSITIONAL':
                            examples['body_text'] = [[param.example for param in component.parameter_ids]]
                        else:
                            examples['body_text_named_params'] = [
                                {'param_name': param.name, 'example': param.example}
                                for param in component.parameter_ids
                            ]
                        comp_data['example'] = examples
                if component.button_ids:
                    buttons = []
                    for button in component.button_ids:
                        button_data = {
                            'type': button.type,
                            'text': button.text,
                        }

                        if button.type == 'PHONE_NUMBER':
                            if button.phone_number:
                                button_data['phone_number'] = button.phone_number
                            else:
                                raise UserError(_('Phone number is required for PHONE_NUMBER buttons.'))
                        elif button.type == 'URL':
                            if button.url:
                                button_data['url'] = button.url
                            else:
                                raise UserError(_('URL is required for URL buttons.'))
                        elif button.type == 'FLOW':
                            if button.flow_id:
                                button_data['flow_id'] = button.flow_id
                            else:
                                raise UserError(_('Flow ID is required for FLOW buttons.'))
                            if button.flow_action:
                                button_data['flow_action'] = button.flow_action
                            if button.navigate_screen:
                                button_data['navigate_screen'] = button.navigate_screen
                            if button.icon:
                                button_data['icon'] = button.icon

                        buttons.append(button_data)
                    comp_data['buttons'] = buttons
                    print(comp_data['buttons'])

                components.append(comp_data)

            payload = {
                'name': self.name,
                'category': self.category,
                'language': self.lang.code.replace('-', '_'),
                'components': components,
            }

            # Create a new template
            url = f"{self.config_id.api_url}/{self.config_id.business_account_id}/message_templates"
            print(payload)
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                data = response.json()
                self.template_id = data.get('id')
                self.add_status = 'added'
                self.status = 'PENDING'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Template created successfully!'),
                        'type': 'success',
                        'sticky': False,
                        "next": {
                            "type": "ir.actions.client",
                            "tag": "reload",
                        },
                    }
                }
            else:
                _logger.error("Failed to create template: %s", response.text)
                raise UserError(_('Failed to create template: %s') % response.text)

        except Exception as e:
            _logger.error("Error creating template: %s", str(e))
            raise UserError(_('Error creating template: %s') % str(e))

    def action_resubmit_template(self):
        """Edit an existing template on Meta."""
        self.ensure_one()
        try:
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
                'Content-Type': 'application/json',
            }
            # Prepare the template data
            components = []
            for component in self.component_ids:
                # Check for parameters in the text (e.g., {{1}}, {{2}})
                if component.text and '{{' in component.text and '}}' in component.text:
                    raise UserError(
                        _('Template text contains parameters (e.g., {{1}}), which are not supported in this implementation. Please remove the parameters and try again.'))

                comp_data = {
                    'type': component.type,
                }
                # Only set the text field for non-BUTTONS components
                if component.type != 'BUTTONS' and component.text:
                    comp_data['text'] = component.text

                if component.type == 'HEADER' and component.format:
                    comp_data['format'] = component.format

                if component.button_ids:
                    buttons = []
                    for button in component.button_ids:
                        button_data = {
                            'type': button.type,
                            'text': button.text,
                        }

                        if button.type == 'PHONE_NUMBER':
                            if button.phone_number:
                                button_data['phone_number'] = button.phone_number
                            else:
                                raise UserError(_('Phone number is required for PHONE_NUMBER buttons.'))
                        elif button.type == 'URL':
                            if button.url:
                                button_data['url'] = button.url
                            else:
                                raise UserError(_('URL is required for URL buttons.'))
                        elif button.type == 'FLOW':
                            if button.flow_id:
                                button_data['flow_id'] = button.flow_id
                            else:
                                raise UserError(_('Flow ID is required for FLOW buttons.'))
                            if button.flow_action:
                                button_data['flow_action'] = button.flow_action
                            if button.navigate_screen:
                                button_data['navigate_screen'] = button.navigate_screen
                            if button.icon:
                                button_data['icon'] = button.icon

                        buttons.append(button_data)
                    comp_data['buttons'] = buttons

                components.append(comp_data)
            if self.status not in ['APPROVED', 'REJECTED', 'PAUSED']:
                raise UserError(_('Only APPROVED, REJECTED, or PAUSED templates can be edited.'))

            payload = {
                'name': self.name,
                # 'category': self.category,
                'language': self.lang.code.replace('-', '_'),
                'components': components,
            }

            if self.status in ['REJECTED', 'PAUSED']:
                payload['category'] = self.category
            _logger.info(payload)

            # Edit an existing template
            if not self.template_id:
                raise UserError(_('Template ID is missing. Cannot edit the template.'))
            # Use the correct API endpoint with version
            # api_version = self.config_id.api_version if hasattr(self.config_id, 'api_version') else 'v18.0'
            url = f"{self.config_id.api_url}/{self.template_id}"
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                self.status = 'PENDING'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Template updated successfully!'),
                        'type': 'success',
                        'sticky': False,
                        'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                    }
                }
            else:
                _logger.error("Failed to update template: %s", response.text)
                raise UserError(_('Failed to update template: %s') % response.text)

        except Exception as e:
            _logger.error("Error updating template: %s", str(e))
            raise UserError(_('Error updating template: %s') % str(e))

    def action_get_status(self):
        """Fetch the current status of the template from Meta."""
        self.ensure_one()
        try:
            url = f"{self.config_id.api_url}/{self.config_id.business_account_id}/message_templates?template_id={self.template_id}"
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
                'Content-Type': 'application/json',
            }
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                templates = data.get('data', [])
                if templates:
                    self.status = templates[0].get('status', 'PENDING')
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Success'),
                            'message': _('Template status updated: %s') % self.status,
                            'type': 'success',
                            'sticky': False,
                            "next": {
                                "type": "ir.actions.client",
                                "tag": "reload",
                            },
                        }
                    }
                else:
                    raise UserError(_('Template not found on Meta.'))
            else:
                _logger.error("Failed to fetch template status: %s", response.text)
                raise UserError(_('Failed to fetch template status: %s') % response.text)
        except Exception as e:
            _logger.error("Error fetching template status: %s", str(e))
            raise UserError(_('Error fetching template status: %s') % str(e))

    def action_remove_template(self):
        """Remove the template from Meta and delete it from Odoo."""
        self.ensure_one()
        try:
            url = f"{self.config_id.api_url}/{self.config_id.business_account_id}/message_templates?name={self.name}"
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
                'Content-Type': 'application/json',
            }
            response = requests.delete(url, headers=headers)
            if response.status_code == 200:
                self.unlink()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Template removed successfully!'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                _logger.error("Failed to remove template: %s", response.text)
                raise UserError(_('Failed to remove template: %s') % response.text)
        except Exception as e:
            _logger.error("Error removing template: %s", str(e))
            raise UserError(_('Error removing template: %s') % str(e))


class WhatsAppTemplateComponent(models.Model):
    _name = 'whatsapp.template.component'
    _description = 'WhatsApp Template Component'

    template_id = fields.Many2one(
        'whatsapp.template',
        string="Template",
        required=True,
        ondelete='cascade',
        help="The template this component belongs to"
    )
    type = fields.Selection(
        [
            ('HEADER', 'Header'),
            ('BODY', 'Body'),
            ('FOOTER', 'Footer'),
            ('BUTTONS', 'Buttons'),
        ],
        string="Component Type",
        required=True,
        help="Type of the component"
    )
    format = fields.Selection(
        [
            ('TEXT', 'Text'),
            ('IMAGE', 'Image'),
            ('VIDEO', 'Video'),
            ('DOCUMENT', 'Document'),
            ('LOCATION', 'Location'),
        ],
        string="Format",
        help="Format for HEADER component (e.g., TEXT, IMAGE, VIDEO, DOCUMENT, LOCATION)"
    )
    text = fields.Text(
        string="Text",
        help="Text content for HEADER, BODY, or FOOTER components"
    )
    button_ids = fields.One2many(
        'whatsapp.template.component.button',
        'component_id',
        string="Buttons",
        help="Button configurations for BUTTONS component"
    )
    parameter_ids = fields.One2many(
        'whatsapp.template.component.parameter',
        'component_id',
        string="Parameters",
        help="Parameters for HEADER or BODY components (e.g., {{1}}, {{sale_start_date}})"
    )


class WhatsAppTemplateComponentButton(models.Model):
    _name = 'whatsapp.template.component.button'
    _description = 'WhatsApp Template Component Button'

    component_id = fields.Many2one(
        'whatsapp.template.component',
        string="Component",
        required=True,
        ondelete='cascade',
        help="The BUTTONS component this button belongs to"
    )
    type = fields.Selection(
        [
            ('PHONE_NUMBER', 'Phone Number'),
            ('URL', 'URL'),
            ('QUICK_REPLY', 'Quick Reply'),
            ('COPY_CODE', 'Copy Code'),
            ('FLOW', 'Flow'),
            ('MPM', 'Multi-Product Message'),
            ('OTP', 'One-Time Password'),
            ('SPM', 'Single-Product Message'),
        ],
        string="Button Type",
        required=True,
        help="Type of the button"
    )
    text = fields.Char(
        string="Button Text",
        help="Button label text (max 25 characters)"
    )
    phone_number = fields.Char(
        string="Phone Number",
        help="Phone number for PHONE_NUMBER buttons"
    )
    url = fields.Char(
        string="URL",
        help="URL for URL buttons"
    )
    flow_id = fields.Char(
        string="Flow ID",
        help="Flow ID for FLOW buttons"
    )
    flow_name = fields.Char(
        string="Flow Name",
        help="Flow name for FLOW buttons"
    )
    flow_action = fields.Selection(
        [
            ('navigate', 'Navigate'),
            ('data_exchange', 'Data Exchange'),
        ],
        string="Flow Action",
        help="Action for FLOW buttons"
    )
    navigate_screen = fields.Char(
        string="Navigate Screen",
        help="Entry screen ID for FLOW buttons"
    )
    icon = fields.Selection(
        [
            ('DOCUMENT', 'Document'),
            ('PROMOTION', 'Promotion'),
            ('REVIEW', 'Review'),
        ],
        string="Icon",
        help="Icon for FLOW buttons"
    )


class WhatsAppTemplateComponentParameter(models.Model):
    _name = 'whatsapp.template.component.parameter'
    _description = 'WhatsApp Template Component Parameter'

    component_id = fields.Many2one(
        'whatsapp.template.component',
        string="Component",
        required=True,
        ondelete='cascade',
        help="The component this parameter belongs to"
    )
    fieldd = fields.Many2one('ir.model.fields', 'field')