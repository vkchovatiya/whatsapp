from odoo import models, fields, api ,_
from odoo.exceptions import UserError
import requests
import string
import secrets
import json
import logging

_logger = logging.getLogger(__name__)

class WhatsAppConfig(models.Model):
    _name = "whatsapp.config"
    _description = "WhatsApp Configuration"
    _rec_name = "name"

    name = fields.Char(string="Provider Name", required=True, help="Name of the WhatsApp provider configuration")
    api_url = fields.Char(
        string="API URL",
        default="https://graph.facebook.com/v20.0",
        required=True,
        help="Base URL for WhatsApp Cloud API"
    )
    instance_id = fields.Char(
        string="Phone Number ID",
        required=True,
        help="Phone Number ID from Meta WhatsApp Business Account"
    )
    business_account_id = fields.Char(
        string="Business Account ID",
        required=True,
        help="WhatsApp Business Account ID from Meta"
    )
    access_token = fields.Char(
        string="Access Token",
        required=True,
        help="Permanent Access Token for WhatsApp API"
    )
    app_id = fields.Char(
        string="App ID",
        required=True,
        help="Facebook App ID from Meta Developer Console"
    )
    operator_ids = fields.Many2many(
        'res.users',
        string="Operators",
        help="Users who can operate this WhatsApp configuration"
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('verified', 'Verified'),
            ('error','Error')

        ],
        string="Status",
        default='draft',
        help="Status of the WhatsApp configuration"
    )
    webhook_url = fields.Char(
        string="Webhook URL",
        readonly=True,
        compute="_compute_webhook_url",
        help="Webhook URL for receiving WhatsApp messages"
    )
    webhook_token = fields.Char(
        string="Webhook Token",
        readonly=True,
        default=lambda self: self._generate_webhook_token(),
        help="Token for verifying Meta webhook requests"
    )
    template_ids = fields.One2many('whatsapp.template', 'config_id', string="Templates")


    verified_name = fields.Char(string="Verified Name", readonly=True, help="Verified name of the phone number")
    code_verification_status = fields.Char(string="Code Verification Status", readonly=True, help="Code verification status of the phone number")
    display_phone_number = fields.Char(string="Display Phone Number", readonly=True, help="Display phone number")
    quality_rating = fields.Char(string="Quality Rating", readonly=True, help="Quality rating of the phone number")
    platform_type = fields.Char(string="Platform Type", readonly=True, help="Platform type of the phone number")
    throughput_level = fields.Char(string="Throughput Level", readonly=True, help="Throughput level of the phone number")
    business_messaging_product = fields.Char(string="Messaging Product", readonly=True,
                                             help="Messaging product used (e.g., whatsapp)")
    business_address = fields.Text(string="Business Address", readonly=True, help="Address of the business")
    business_description = fields.Text(string="Business Description", readonly=True, help="Description of the business")
    business_vertical = fields.Char(string="Business Vertical", readonly=True, help="Industry type of the business")
    business_about = fields.Char(string="Business About", readonly=True,)
    business_email = fields.Char(string="Business Email", readonly=True, help="Contact email address of the business")
    business_websites = fields.Char(string="Business Websites", readonly=True,)

    @api.depends('name')
    def _compute_webhook_url(self):
        """Compute the webhook URL based on Odoo's base URL and provider ID."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.webhook_url = f"{base_url}/whatsapp/webhook/{record.id}"

    def _generate_webhook_token(self):
        """Generate a secure webhook token for Meta verification."""
        characters = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(characters) for _ in range(32))

    def action_regenerate_webhook_token(self):
        """Regenerate the webhook token and notify user to update Meta."""
        self.ensure_one()
        self.write({'webhook_token': self._generate_webhook_token()})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Webhook token regenerated. Update the Verify Token in Meta App Dashboard.'),
                'type': 'success',
                'sticky': True,
            }
        }

    def get_business_profile(self):
        """Fetch the WhatsApp Business Profile details and update the record."""
        self.ensure_one()
        try:
            url = f"{self.api_url}/{self.instance_id}/whatsapp_business_profile?fields=messaging_product,address,description,vertical,about,email,websites"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
            }
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                profile_data = data.get('data', [{}])[0]
                print(profile_data.get('websites'))
                self.write({
                    'business_address': profile_data.get('address', ''),
                    'business_description': profile_data.get('description', ''),
                    'business_vertical': profile_data.get('vertical', ''),
                    'business_about': profile_data.get('about', ''),
                    'business_email': profile_data.get('email', ''),
                    'business_websites': json.dumps(profile_data.get('websites', [])),

                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Business profile details fetched successfully!'),
                        'type': 'success',
                        'sticky': False,
                        "next": {
                            "type": "ir.actions.client",
                            "tag": "reload",
                        },
                    }
                }
            else:
                _logger.error("Failed to fetch business profile: %s", response.text)
                raise UserError(_('Failed to fetch business profile: %s') % response.text)
        except Exception as e:
            _logger.error("Error fetching business profile: %s", str(e))
            raise UserError(_('Error fetching business profile: %s') % str(e))
            
    def action_verify_configuration(self):
        """Verify the WhatsApp configuration by making a test API call."""
        self.ensure_one()
        try:
            url = f"{self.api_url}/{self.instance_id}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
            }
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                self.write({'state': 'verified'})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('WhatsApp configuration verified successfully!'),
                        'type': 'success',
                        'sticky': False,
                        "next": {
                            "type": "ir.actions.client",
                            "tag": "reload",
                        },
                    }

                }
            else:
                self.write({'state': 'error'})
                raise UserError(_('Failed to verify configuration: %s') % response.text)
        except Exception as e:
            self.write({'state': 'error'})
            raise UserError(_('Error verifying configuration: %s') % str(e))

    def action_reset_to_draft(self):
        """Reset the configuration status to draft."""
        self.write({'state': 'draft'})

    def get_message_template(self):
        """Fetch message templates from Meta API and create/update them in Odoo."""
        self.ensure_one()
        try:
            url = f"{self.api_url}/{self.business_account_id}/message_templates"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
            }
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                _logger.error("Failed to fetch templates: %s", response.text)
                raise UserError(_('Failed to fetch templates: %s') % response.text)

            data = response.json()
            templates = data.get('data', [])
            _logger.info("Fetched %s templates for config ID %s", len(templates), self.id)

            language_mapping = {
                'en': 'en_US',
            }
            template_model = self.env['whatsapp.template']
            component_model = self.env['whatsapp.template.component']
            button_model = self.env['whatsapp.template.component.button']
            button_app_model = self.env['whatsapp.template.component.button.app']
            parameter_model = self.env['whatsapp.template.component.parameter']

            for template in templates:
                meta_language = template.get('language')
                odoo_lang_code = language_mapping.get(meta_language, meta_language.replace('_', '-'))
                lang = self.env['res.lang'].search([('code', 'in', [odoo_lang_code, odoo_lang_code.replace('-', '_')])], limit=1)

                if not lang:
                    _logger.warning("Language code %s not found in res.lang for template %s", meta_language, template.get('name'))
                    continue

                existing_template = template_model.search([
                    ('template_id', '=', template.get('id')),
                    ('config_id', '=', self.id)
                ], limit=1)

                template_data = {
                    'name': template.get('name'),
                    'template_id': template.get('id'),
                    'lang': lang.id,
                    'category': template.get('category'),
                    'status': template.get('status', 'PENDING'),
                    'parameter_format': 'POSITIONAL' if template.get('category') in ['MARKETING', 'UTILITY'] else 'STRUCTURED',
                    'config_id': self.id,
                    'add_status': 'added' if template.get('status') else 'new',
                }

                if existing_template:
                    existing_template.write(template_data)
                    existing_template.component_ids.unlink()
                    template_id = existing_template.id
                    _logger.info("Updated template %s (ID: %s)", template.get('name'), template.get('id'))
                else:
                    new_template = template_model.create(template_data)
                    template_id = new_template.id
                    _logger.info("Created template %s (ID: %s)", template.get('name'), template.get('id'))

                for comp in template.get('components', []):
                    comp_data = {
                        'template_id': template_id,
                        'type': comp.get('type'),
                        'format': comp.get('format'),
                        'text': comp.get('text'),
                        'add_security_recommendation': comp.get('add_security_recommendation', False) if comp.get('type') == 'BODY' else False,
                        'code_expiration_minutes': comp.get('code_expiration_minutes') if comp.get('type') == 'FOOTER' else False,
                        'location_latitude': comp.get('latitude') if comp.get('type') == 'HEADER' and comp.get('format') == 'LOCATION' else False,
                        'location_longitude': comp.get('longitude') if comp.get('type') == 'HEADER' and comp.get('format') == 'LOCATION' else False,
                        'location_name': comp.get('name') if comp.get('type') == 'HEADER' and comp.get('format') == 'LOCATION' else False,
                        'location_address': comp.get('address') if comp.get('type') == 'HEADER' and comp.get('format') == 'LOCATION' else False,
                    }
                    component = component_model.create(comp_data)

                    if comp.get('type') == 'BUTTONS' and comp.get('buttons'):
                        for btn in comp.get('buttons', []):
                            btn_data = {
                                'component_id': component.id,
                                'type': btn.get('type'),
                                'text': btn.get('text'),
                                'phone_number': btn.get('phone_number'),
                                'url': btn.get('url'),
                                'otp_type': btn.get('otp_type') if btn.get('type') == 'OTP' else False,
                                'autofill_text': btn.get('autofill_text') if btn.get('type') == 'OTP' and btn.get('otp_type') == 'ONE_TAP' else False,
                            }
                            button = button_model.create(btn_data)

                            if btn.get('type') == 'OTP' and btn.get('supported_apps'):
                                for app in btn.get('supported_apps', []):
                                    app_data = {
                                        'button_id': button.id,
                                        'platform': app.get('id'),
                                        'package_name': app.get('package_name') if app.get('id') == 'android' else False,
                                        'signature_hash': app.get('signature_hash') if app.get('id') == 'android' else False,
                                        'bundle_id': app.get('bundle_id') if app.get('id') == 'ios' else False,
                                    }
                                    button_app_model.create(app_data)

                    if comp.get('type') in ['HEADER', 'BODY'] and comp.get('example'):
                        example = comp.get('example', {})
                        if 'header_text' in example or 'body_text' in example:
                            param_list = example.get('header_text') or example.get('body_text', [[]])[0]
                            for i, ex in enumerate(param_list, 1):
                                parameter_model.create({
                                    'component_id': component.id,
                                    'name': str(i),
                                    'example': ex,
                                })
                        elif 'header_text_named_params' in example or 'body_text_named_params' in example:
                            param_list = example.get('header_text_named_params') or example.get('body_text_named_params', [])
                            for param in param_list:
                                parameter_model.create({
                                    'component_id': component.id,
                                    'name': param.get('param_name'),
                                    'example': param.get('example'),
                                })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Successfully fetched and updated %s templates.') % len(templates),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error("Error fetching templates: %s", str(e))
            raise UserError(_('Error fetching templates: %s') % str(e))

    def get_phone_number_details(self):
        """Fetch phone number details from Meta API and update the record."""
        self.ensure_one()
        try:
            url = f"{self.api_url}/{self.instance_id}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
            }
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                _logger.error("Failed to fetch phone number details: %s", response.text)
                raise UserError(_('Failed to fetch phone number details: %s') % response.text)

            data = response.json()
            self.write({
                'verified_name': data.get('verified_name'),
                'code_verification_status': data.get('code_verification_status'),
                'display_phone_number': data.get('display_phone_number'),
                'quality_rating': data.get('quality_rating'),
                'platform_type': data.get('platform_type'),
                'throughput_level': data.get('throughput', {}).get('level'),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Phone number details fetched successfully!'),
                    'type': 'success',
                    'sticky': False,
                    "next": {
                        "type": "ir.actions.client",
                        "tag": "reload",
                    },
                }

            }
        except Exception as e:
            _logger.error("Error fetching phone number details: %s", str(e))
            raise UserError(_('Error fetching phone number details: %s') % str(e))