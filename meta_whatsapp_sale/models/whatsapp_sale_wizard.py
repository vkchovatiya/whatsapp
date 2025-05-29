# -*- coding: utf-8 -*-
# Part of Creyox Technologies.

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging
import base64

_logger = logging.getLogger(__name__)

class WhatsAppSaleWizard(models.TransientModel):
    _name = 'whatsapp.sale.wizard'
    _description = 'Wizard to Send WhatsApp Messages for Sales'

    sale_order_id = fields.Many2one(
        'sale.order',
        string="Sale Order",
        required=True,
        default=lambda self: self.env.context.get('default_sale_order_id')
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True,
        default=lambda self: self.env.context.get('default_partner_id')
    )
    phone = fields.Char(
        string="Phone Number",
        required=True,
        default=lambda self: self.env.context.get('default_phone')
    )
    template_id = fields.Many2one(
        'whatsapp.template',
        string="Template",
        help="Select a WhatsApp message template"
    )
    message = fields.Text(
        string="Message",
        compute='_compute_message',
        store=True,
        readonly=False,
        help="Message content, populated from template or custom"
    )
    config_id = fields.Many2one(
        'whatsapp.config',
        string="WhatsApp Provider",
        required=True,
        default=lambda self: self.env['whatsapp.config'].search([], limit=1)
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string="Attachments",
        help="Attach media files (doc, PDF, image, video, audio)"
    )

    @api.depends('template_id', 'sale_order_id')
    def _compute_message(self):
        """Populate message from template, replacing placeholders."""
        for wizard in self:
            if wizard.template_id and wizard.sale_order_id:
                # Replace placeholders (e.g., {{partner_name}}, {{order_name}})
                message = wizard.template_id.message
                message = message.replace('{{partner_name}}', wizard.partner_id.name or '')
                message = message.replace('{{order_name}}', wizard.sale_order_id.name or '')
                message = message.replace('{{amount_total}}', str(wizard.sale_order_id.amount_total) or '')
                wizard.message = message
            else:
                wizard.message = False

    @api.constrains('phone')
    def _check_phone(self):
        """Validate phone number format."""
        for wizard in self:
            if not wizard.phone or not any(c.isdigit() for c in wizard.phone):
                raise ValidationError(_('Please provide a valid phone number.'))

    def action_send_message(self):
        """Send WhatsApp message with template and attachments."""
        self.ensure_one()
        if not self.config_id or not (self.template_id or self.message):
            raise UserError(_('Please select a WhatsApp provider and a template or enter a message.'))

        # Prepare phone number
        phone = self.phone.replace('+', '').replace(' ', '')
        if not phone.isdigit():
            raise UserError(_('Invalid phone number format.'))

        # Prepare API request
        headers = {
            'Authorization': f'Bearer {self.config_id.access_token}',
            'Content-Type': 'application/json',
        }
        url = f"{self.config_id.api_url}/{self.config_id.instance_id}/messages"
        message_history = self.env['whatsapp.message.history']

        try:
            # Send template-based message if template_id is set
            if self.template_id:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "template",
                    "template": {
                        "name": self.template_id.name,
                        "language": {
                            "code": self.template_id.lang.code.replace('-', '_')
                        },
                        "components": []
                    }
                }
                response = requests.post(url, headers=headers, json=payload)
                _logger.info('WhatsApp template API response for %s: %s', phone, response.text)
                response.raise_for_status()
                response_data = response.json()
                message_id = response_data.get('messages', [{}])[0].get('id')
                conversation_id = response_data.get('conversations', [{}])[0].get('id', False)

                # Log template message
                history_vals = {
                    'campaign_id': False,
                    'partner_id': self.partner_id.id,
                    'number': phone,
                    'user': self.env.user.id,
                    'date': fields.Datetime.now(),
                    'message': self.message,
                    'config_id': self.config_id.id,
                    'template_id': self.template_id.id,
                    'status': 'sent',
                    'message_id': message_id,
                    'conversation_id': conversation_id,
                    # 'sale_order_id': self.sale_order_id.id,
                }
                message_history.create(history_vals)

            # Send text message if no template
            else:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "text",
                    "text": {
                        "body": self.message
                    }
                }
                response = requests.post(url, headers=headers, json=payload)
                _logger.info('WhatsApp text API response for %s: %s', phone, response.text)
                response.raise_for_status()
                response_data = response.json()
                message_id = response_data.get('messages', [{}])[0].get('id')
                conversation_id = response_data.get('conversations', [{}])[0].get('id', False)

                # Log text message
                history_vals = {
                    'campaign_id': False,
                    'partner_id': self.partner_id.id,
                    'number': phone,
                    'user': self.env.user.id,
                    'date': fields.Datetime.now(),
                    'message': self.message,
                    'config_id': self.config_id.id,
                    'template_id': False,
                    'status': 'sent',
                    'message_id': message_id,
                    'conversation_id': conversation_id,
                    # 'sale_order_id': self.sale_order_id.id,
                }
                message_history.create(history_vals)

            # Send attachments
            for attachment in self.attachment_ids:
                mime_type = attachment.mimetype
                file_data = base64.b64decode(attachment.datas)
                # Determine media type
                media_type = 'document'
                if mime_type.startswith('image'):
                    media_type = 'image'
                elif mime_type.startswith('video'):
                    media_type = 'video'
                elif mime_type.startswith('audio'):
                    media_type = 'audio'

                # Upload media to WhatsApp
                upload_url = f"{self.config_id.api_url}/{self.config_id.instance_id}/media"
                files = {'file': (attachment.name, file_data, mime_type)}
                upload_response = requests.post(upload_url, headers={'Authorization': f'Bearer {self.config_id.access_token}'}, files=files)
                _logger.info('WhatsApp media upload response for %s: %s', attachment.name, upload_response.text)
                upload_response.raise_for_status()
                media_id = upload_response.json().get('id')

                # Send media message
                media_payload = {
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": media_type,
                    media_type: {
                        "id": media_id
                    }
                }
                if media_type == 'document':
                    media_payload[media_type]['filename'] = attachment.name

                media_response = requests.post(url, headers=headers, json=media_payload)
                _logger.info('WhatsApp media API response for %s: %s', phone, media_response.text)
                media_response.raise_for_status()
                media_response_data = media_response.json()
                media_message_id = media_response_data.get('messages', [{}])[0].get('id')

                # Log media message
                history_vals = {
                    'campaign_id': False,
                    'partner_id': self.partner_id.id,
                    'number': phone,
                    'user': self.env.user.id,
                    'date': fields.Datetime.now(),
                    'message': f"Sent attachment: {attachment.name}",
                    'config_id': self.config_id.id,
                    'template_id': False,
                    'status': 'sent',
                    'message_id': media_message_id,
                    'conversation_id': conversation_id,
                    # 'sale_order_id': self.sale_order_id.id,
                    'attachment_id': attachment.id,
                }
                message_history.create(history_vals)

        except requests.RequestException as e:
            _logger.error("Failed to send WhatsApp message to %s: %s", phone, str(e))
            history_vals = {
                'campaign_id': False,
                'partner_id': self.partner_id.id,
                'number': phone,
                'user': self.env.user.id,
                'date': fields.Datetime.now(),
                'message': self.message or 'Attachment sending failed',
                'config_id': self.config_id.id,
                'template_id': self.template_id.id if self.template_id else False,
                'status': 'failed',
                'error': str(e),
                # 'sale_order_id': self.sale_order_id.id,
            }
            message_history.create(history_vals)
            raise UserError(_('Failed to send message: %s') % str(e))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Message sent successfully to %s.') % self.partner_id.name,
                'type': 'success',
                'sticky': False,
            }
        }