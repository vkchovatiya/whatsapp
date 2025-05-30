# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
import requests
import base64
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
    type = fields.Selection([
        ('message', 'Message'),
        ('interactive', 'Interactive'),
    ], string="Type", help="Template Type")
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
        store=True,
        readonly=False,
    )
    parameter_mapping_ids = fields.One2many(
        'whatsapp.template.parameter.mapping',
        'template_id',
        string="Parameter Mappings",
        help="Mappings of template parameters to model fields for auto-filling"
    )

    @api.depends('component_ids', 'component_ids.text')
    def _compute_message(self):
        for record in self:
            body_component = record.component_ids.filtered(lambda c: c.type == 'BODY')
            record.message = body_component.text if body_component and body_component.text else False

    def _inverse_message(self):
        for record in self:
            body_component = record.component_ids.filtered(lambda c: c.type == 'BODY')
            if record.message and record.category != 'AUTHENTICATION':
                if body_component:
                    body_component.text = record.message
                else:
                    record.component_ids = [(0, 0, {
                        'type': 'BODY',
                        'text': record.message,
                    })]
            else:
                if body_component and body_component.text:
                    body_component.text = False

    def _upload_media(self, component):
        if not component.media_file:
            raise UserError(_('No media file provided for %s format.') % component.format)

        headers = {
            'Authorization': f'Bearer {self.config_id.access_token}',
        }
        mime_types = {
            'IMAGE': 'image/jpeg',
            'VIDEO': 'video/mp4',
            'DOCUMENT': 'application/pdf',
        }
        media_type = mime_types.get(component.format, 'application/octet-stream')
        files = {
            'file': (component.media_filename or f'media.{component.format.lower()}', base64.b64decode(component.media_file), media_type),
            'type': (None, component.format.lower()),
            'messaging_product': (None, 'whatsapp'),
        }
        url = f"{self.config_id.api_url}/{self.config_id.phone_number_id}/media"
        response = requests.post(url, headers=headers, files=files)
        if response.status_code in [200, 201]:
            data = response.json()
            media_id = data.get('id')
            if not media_id:
                raise UserError(_('Media upload failed: No media ID returned.'))
            return media_id
        else:
            _logger.error("Failed to upload media: %s", response.text)
            raise UserError(_('Failed to upload media: %s') % response.text)

    def action_create_template(self):
        self.ensure_one()
        try:
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
                'Content-Type': 'application/json',
            }
            components = []
            for component in self.component_ids:
                # Skip HEADER for AUTHENTICATION templates
                if self.category == 'AUTHENTICATION' and component.type == 'HEADER':
                    continue

                comp_data = {
                    'type': component.type,
                }
                if component.type == 'HEADER':
                    comp_data['format'] = component.format
                    if component.format == 'TEXT' and component.text:
                        comp_data['text'] = component.text
                         
                    elif component.format in ['IMAGE', 'VIDEO', 'DOCUMENT'] and component.media_file:
                        media_id = self._upload_media(component)
                        comp_data['example'] = {'header_handle': [media_id]}
                    elif component.format == 'LOCATION' and component.location_latitude and component.location_longitude:
                        comp_data['latitude'] = component.location_latitude
                        comp_data['longitude'] = component.location_longitude
                        if component.location_name:
                            comp_data['name'] = component.location_name
                        if component.location_address:
                            comp_data['address'] = component.location_address
                elif component.type == 'BODY':
                    if self.category in ['MARKETING', 'UTILITY'] and component.text:
                        comp_data['text'] = component.text
                    if self.category == 'AUTHENTICATION' and component.add_security_recommendation:
                        comp_data['add_security_recommendation'] = component.add_security_recommendation
                   
                elif component.type == 'FOOTER':
                    if component.text:
                        comp_data['text'] = component.text
                    if self.category == 'AUTHENTICATION' and component.code_expiration_minutes:
                        comp_data['code_expiration_minutes'] = component.code_expiration_minutes
                elif component.type == 'BUTTONS' and component.button_ids:
                    buttons = []
                    for button in component.button_ids:
                        button_data = {
                            'type': button.type,
                            'text': button.text,
                        }
                        if button.type == 'PHONE_NUMBER' and button.phone_number:
                            button_data['phone_number'] = button.phone_number
                        elif button.type == 'URL' and button.url:
                            button_data['url'] = button.url
                            if button.example:
                                button_data['example'] = [button.example]
                        elif button.type == 'OTP':
                            button_data['otp_type'] = button.otp_type
                            if button.app_ids:
                                supported_apps = []
                                for app in button.app_ids:
                                    app_data = {}
                                    if app.platform == 'android':
                                        if app.package_name:
                                            app_data['package_name'] = app.package_name
                                        if app.signature_hash:
                                            app_data['signature_hash'] = app.signature_hash
                                    elif app.platform == 'ios':
                                        if app.bundle_id:
                                            app_data['bundle_id'] = app.bundle_id
                                    supported_apps.append(app_data)
                                button_data['supported_apps'] = supported_apps
                            if button.otp_type == 'ONE_TAP':
                                button_data['autofill_text'] = button.autofill_text
                        elif button.type in ['QUICK_REPLY', 'CATALOG', 'MPM', 'COPY_CODE', 'SPM']:
                            pass
                        buttons.append(button_data)
                    comp_data['buttons'] = buttons

                components.append(comp_data)

            payload = {
                'name': self.name,
                'category': self.category,
                'language': self.lang.code.replace('-', '_'),
                'components': components,
            }

            url = f"{self.config_id.api_url}/{self.config_id.business_account_id}/message_templates"
            _logger.info("Creating template with payload: %s", payload)
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
                        'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                    }
                }
            else:
                _logger.error("Failed to create template: %s", response.text)
                raise UserError(_('Failed to create template: %s') % response.text)

        except Exception as e:
            _logger.error("Error creating template: %s", str(e))
            raise UserError(_('Error creating template: %s') % str(e))

    def action_resubmit_template(self):
        self.ensure_one()
        try:
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
                'Content-Type': 'application/json',
            }
            components = []
            for component in self.component_ids:
                # Skip HEADER for AUTHENTICATION templates
                if self.category == 'AUTHENTICATION' and component.type == 'HEADER':
                    continue

                comp_data = {
                    'type': component.type,
                }
                if component.type == 'HEADER':
                    comp_data['format'] = component.format
                    if component.format == 'TEXT' and component.text:
                        comp_data['text'] = component.text
                         
                    elif component.format in ['IMAGE', 'VIDEO', 'DOCUMENT'] and component.media_file:
                        media_id = self._upload_media(component)
                        comp_data['example'] = {'header_handle': [media_id]}
                    elif component.format == 'LOCATION' and component.location_latitude and component.location_longitude:
                        comp_data['latitude'] = component.location_latitude
                        comp_data['longitude'] = component.location_longitude
                        if component.location_name:
                            comp_data['name'] = component.location_name
                        if component.location_address:
                            comp_data['address'] = component.location_address
                elif component.type == 'BODY':
                    if self.category in ['MARKETING', 'UTILITY'] and component.text:
                        comp_data['text'] = component.text
                    if self.category == 'AUTHENTICATION' and component.add_security_recommendation:
                        comp_data['add_security_recommendation'] = component.add_security_recommendation
                     
                elif component.type == 'FOOTER':
                    if component.text:
                        comp_data['text'] = component.text
                    if self.category == 'AUTHENTICATION' and component.code_expiration_minutes:
                        comp_data['code_expiration_minutes'] = component.code_expiration_minutes
                elif component.type == 'BUTTONS' and component.button_ids:
                    buttons = []
                    for button in component.button_ids:
                        button_data = {
                            'type': button.type,
                            'text': button.text,
                        }
                        if button.type == 'PHONE_NUMBER' and button.phone_number:
                            button_data['phone_number'] = button.phone_number
                        elif button.type == 'URL' and button.url:
                            button_data['url'] = button.url
                            if button.example:
                                button_data['example'] = [button.example]
                        elif button.type == 'OTP':
                            button_data['otp_type'] = button.otp_type
                            if button.app_ids:
                                supported_apps = []
                                for app in button.app_ids:
                                    app_data = {'id': app.platform}
                                    if app.platform == 'android':
                                        if app.package_name:
                                            app_data['package_name'] = app.package_name
                                        if app.signature_hash:
                                            app_data['signature_hash'] = app.signature_hash
                                    elif app.platform == 'ios':
                                        if app.bundle_id:
                                            app_data['bundle_id'] = app.bundle_id
                                    supported_apps.append(app_data)
                                button_data['supported_apps'] = supported_apps
                            if button.otp_type == 'ONE_TAP':
                                button_data['autofill_text'] = button.autofill_text
                        elif button.type in ['QUICK_REPLY', 'CATALOG', 'MPM', 'COPY_CODE', 'SPM']:
                            pass
                        buttons.append(button_data)
                    comp_data['buttons'] = buttons

                components.append(comp_data)

            if self.status not in ['APPROVED', 'REJECTED', 'PAUSED']:
                raise UserError(_('Only APPROVED, REJECTED, or PAUSED templates can be edited.'))

            payload = {
                'name': self.name,
                'language': self.lang.code.replace('-', '_'),
                'components': components,
            }
            if self.status in ['REJECTED', 'PAUSED']:
                payload['category'] = self.category

            if not self.template_id:
                raise UserError(_('Template ID is missing. Cannot edit the template.'))

            url = f"{self.config_id.api_url}/{self.template_id}"
            _logger.info("Updating template with payload: %s", payload)
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
                            'next': {
                                'type': 'ir.actions.client',
                                'tag': 'reload',
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
        help="Text content for HEADER (TEXT format), BODY (MARKETING/UTILITY), or FOOTER components"
    )
    media_file = fields.Binary(
        string="Media File",
        help="Media file for IMAGE, VIDEO, or DOCUMENT header formats"
    )
    media_filename = fields.Char(
        string="Media Filename",
        help="Filename for the media file"
    )
    location_latitude = fields.Float(
        string="Latitude",
        digits=(16, 12),
        help="Latitude for LOCATION header format"
    )
    location_longitude = fields.Float(
        string="Longitude",
        digits=(16, 12),
        help="Longitude for LOCATION header format"
    )
    location_name = fields.Char(
        string="Location Name",
        help="Name of the location for LOCATION header format"
    )
    location_address = fields.Char(
        string="Location Address",
        help="Address of the location for LOCATION header format"
    )
    add_security_recommendation = fields.Boolean(
        string="Add Security Recommendation",
        help="Add security recommendation text to BODY component (for AUTHENTICATION templates)"
    )
    code_expiration_minutes = fields.Integer(
        string="Code Expiration Minutes",
        help="Expiration time for authentication code in minutes (for FOOTER in AUTHENTICATION templates)"
    )
    button_ids = fields.One2many(
        'whatsapp.template.component.button',
        'component_id',
        string="Buttons",
        help="Button configurations for BUTTONS component"
    )

    @api.constrains('format', 'type', 'text', 'media_file', 'location_latitude', 'location_longitude', 'add_security_recommendation')
    def _check_component_format(self):
        for component in self:
            if component.type == 'HEADER' and component.template_id.category != 'AUTHENTICATION':
                if component.format == 'TEXT' and not component.text:
                    raise UserError(_('Text is required for HEADER components with TEXT format.'))
                elif component.format in ['IMAGE', 'VIDEO', 'DOCUMENT'] and not component.media_file:
                    raise UserError(_('Media file is required for HEADER components with %s format.') % component.format)
                elif component.format == 'LOCATION' and (not component.location_latitude or not component.location_longitude):
                    raise UserError(_('Latitude and Longitude are required for HEADER components with LOCATION format.'))
                elif not component.format:
                    if any([component.text, component.media_file, component.location_latitude, component.location_longitude, component.location_name, component.location_address]):
                        raise UserError(_('No format selected for HEADER component, but data fields are filled. Please select a format or clear the fields.'))
            elif component.type == 'HEADER' and component.template_id.category == 'AUTHENTICATION':
                raise UserError(_('HEADER components are not allowed for AUTHENTICATION templates.'))
            elif component.type == 'BODY':
                if component.template_id.category in ['MARKETING', 'UTILITY'] and not component.text:
                    raise UserError(_('Text or parameters are required for BODY components in MARKETING or UTILITY templates.'))
                
            elif component.type == 'FOOTER' and component.template_id.category == 'AUTHENTICATION' and not component.code_expiration_minutes:
                raise UserError(_('Code Expiration Minutes is required for FOOTER components in AUTHENTICATION templates.'))

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
            ('MPM', 'Multi-Product Message'),
            ('OTP', 'One-Time Password'),
            ('SPM', 'Single-Product Message'),
            ('CATALOG', 'Catalog'),
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
    example = fields.Char(
        string="URL Example",
        help="Example value for dynamic URL parameters"
    )
    otp_type = fields.Selection(
        [
            ('COPY_CODE', 'Copy Code'),
            ('ONE_TAP', 'One Tap'),
        ],
        string="OTP Type",
        help="Type of OTP button (for AUTHENTICATION templates)"
    )
    autofill_text = fields.Char(
        string="Autofill Text",
        help="Text for ONE_TAP OTP button"
    )
    app_ids = fields.One2many(
        'whatsapp.template.component.button.app',
        'button_id',
        string="Supported Apps",
        help="Supported apps for OTP buttons"
    )

    @api.constrains('type', 'otp_type', 'text', 'app_ids')
    def _check_button_format(self):
        for button in self:
            if button.type == 'OTP':
                if not button.otp_type:
                    raise UserError(_('OTP Type is required for OTP buttons.'))
                if button.component_id.template_id.category != 'AUTHENTICATION':
                    raise UserError(_('OTP buttons are only allowed in AUTHENTICATION templates.'))
                if not button.app_ids:
                    raise UserError(_('At least one supported app is required for OTP buttons.'))
            if not button.text:
                raise UserError(_('Button Text is required for all buttons.'))

class WhatsAppTemplateComponentButtonApp(models.Model):
    _name = 'whatsapp.template.component.button.app'
    _description = 'WhatsApp Template Component Button Supported App'

    button_id = fields.Many2one(
        'whatsapp.template.component.button',
        string="Button",
        required=True,
        ondelete='cascade',
        help="The button this app configuration belongs to"
    )
    platform = fields.Selection(
        [
            ('android', 'Android'),
            ('ios', 'iOS'),
        ],
        string="Platform",
        required=True,
        help="Platform of the supported app"
    )
    package_name = fields.Char(
        string="Package Name",
        help="App package name for Android"
    )
    signature_hash = fields.Char(
        string="Signature Hash",
        help="Signature hash for Android"
    )
    bundle_id = fields.Char(
        string="Bundle ID",
        help="Bundle ID for iOS"
    )

    @api.constrains('platform', 'package_name', 'signature_hash', 'bundle_id')
    def _check_app_format(self):
        for app in self:
            if app.platform == 'android':
                if not app.package_name:
                    raise UserError(_('Package Name is required for Android apps.'))
                if not app.signature_hash:
                    raise UserError(_('Signature Hash is required for Android apps.'))
            elif app.platform == 'ios':
                if not app.bundle_id:
                    raise UserError(_('Bundle ID is required for iOS apps.'))

    @api.constrains('platform', 'button_id')
    def _check_unique_platform(self):
        for app in self:
            if self.search_count([
                ('button_id', '=', app.button_id.id),
                ('platform', '=', app.platform),
                ('id', '!=', app.id),
            ]):
                raise UserError(_('Each platform can only be specified once per button.'))

class WhatsAppTemplateParameterMapping(models.Model):
    _name = 'whatsapp.template.parameter.mapping'
    _description = 'WhatsApp Template Parameter Mapping'
  

    template_id = fields.Many2one(
        'whatsapp.template',
        string="Template",
        required=True,
        ondelete='cascade',
        help="The template this mapping belongs to"
    )
    parameter_name = fields.Char(
        string="Parameter Name",
        required=True,
        help="Name of the parameter (e.g., 1 for {{1}}, sale_start_date for {{sale_start_date}})"
    )
    field_id = fields.Many2one(
        'ir.model.fields',
        string="Field", 
        required=True,
        ondelete='cascade',
        help="Model field to auto-fill this parameter",
    )

    @api.constrains('parameter_name', 'template_id')
    def _check_unique_mapping(self):
        for record in self:
            domain = [
                ('template_id', '=', record.template_id.id),
                ('id', '!=', record.id),
                ('parameter_name', '=', record.parameter_name), 
            ]
            if self.search_count(domain):
                raise UserError(_('Parameter name must be unique per template.'))

   