# -*- coding: utf-8 -*-
import base64
from odoo.exceptions import UserError 
import requests
from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)

class MessageConfiguration(models.TransientModel):
    _name = 'message.configuration'
    _description = 'WhatsApp Message Configuration'

    recipient = fields.Many2one(
        'res.partner',
        string="Recipient",
        required=True,
    )
    model = fields.Many2one(
        'ir.model',
        string="model", 
    )
    message = fields.Text(
        string="Message",
        help="Message to send to the recipient"
    )
    config_id = fields.Many2one(
        'whatsapp.config',
        string="Configuration",
        required=True,
        domain="[('id', 'in', allowed_config_ids)]",
        help="Select the WhatsApp configuration to use for sending the message"
    )
    allowed_config_ids = fields.Many2many(
        'whatsapp.config',
        string="Allowed Configurations",
        compute="_compute_allowed_config_ids",
    )
    number = fields.Selection(
        [('phone', 'Phone'), ('mobile', 'Mobile')],
        string="Number",
        default='phone',
    )
    template_id = fields.Many2one(
        'whatsapp.template',
        string="Template",
        help="Select a template to populate the message field" ,domain="[('config_id', '=', config_id), ('status', '=', 'APPROVED'), '|', ('available', '=', False), ('available', '=', model)]" )
    attachment = fields.Binary(
        string="Attachment",
        help="Attach a file (e.g., image, document) to send with the message"
    )
    attachment_filename = fields.Char(
        string="Attachment Filename",
        help="Filename of the attachment"
    )
 
  
    @api.depends('config_id')
    def _compute_allowed_config_ids(self):
        for record in self:
            record.allowed_config_ids = record.env.user.allowed_providers

    @api.model
    def default_get(self, fields_list):
        res = super(MessageConfiguration, self).default_get(fields_list)
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')

        if 'config_id' in fields_list and not res.get('config_id'):
            default_provider = self.env.user.default_provider
            if default_provider and default_provider in self.env.user.allowed_providers:
                res['config_id'] = default_provider.id

        if 'recipient' in fields_list and active_model and active_id and not res.get('recipient'):
            if active_model == 'res.partner':
                res['recipient'] = active_id
            elif active_model == 'sale.order':
                order = self.env['sale.order'].browse(active_id)
                if order.partner_id:
                    res['recipient'] = order.partner_id.id

        if 'model' in fields_list and active_model and not res.get('model'):
            model = self.env['ir.model'].search([('model', '=', active_model)], limit=1)
            if model:
                res['model'] = model.id

        return res

    @api.onchange('config_id')
    def _onchange_config_id(self):
        self.template_id = False
        return {
            'domain': {
                'template_id': [('config_id', '=', self.config_id.id), ('status', '=', 'APPROVED')],
                'config_id': [('id', 'in', self.env.user.allowed_providers.ids)]
            }
        }

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id:
            self.message = self.template_id.message
        else:
            self.message = False

    def _upload_media(self):
        """Upload media attachment to WhatsApp API and return media_id, media_type, file_data, filename."""
        if not self.attachment:
            return None, None, None, None

        try:
            file_data = base64.b64decode(self.attachment)
            filename = self.attachment_filename.lower()
            if filename.endswith(('.jpg', '.jpeg', '.png')):
                media_type = 'image'
                mime_type = 'image/jpeg' if filename.endswith(('.jpg', '.jpeg')) else 'image/png'
            elif filename.endswith('.pdf'):
                media_type = 'document'
                mime_type = 'application/pdf'
            elif filename.endswith(('.mp4', '.3gp')):
                media_type = 'video'
                mime_type = 'video/mp4'
            elif filename.endswith(('.mp3', '.amr')):
                media_type = 'audio'
                mime_type = 'audio/mp3'
            else:
                raise UserError(_('Unsupported file type. Supported types: image (jpg, png), document (pdf), video (mp4, 3gp), audio (mp3, amr).'))

            url = f"{self.config_id.api_url}/{self.config_id.instance_id}/media"
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
            }
            files = {
                'file': (self.attachment_filename, file_data, mime_type),
                'messaging_product': (None, 'whatsapp'),
                'type': (None, media_type),
            }
            response = requests.post(url, headers=headers, files=files)
            if response.status_code != 200: 
                raise UserError(_('Failed to upload media: %s') % response.text)

            media_id = response.json().get('id')
            if not media_id:
                raise UserError(_('Media ID not found in response.'))

            return media_id, media_type, file_data, self.attachment_filename

        except Exception as e: 
            raise UserError(_('Error uploading media: %s') % str(e))

 
    def action_send_message(self):
        self.ensure_one()
        at_least_one_success = False
        any_attempt_made = False
    
        number = self.recipient.phone if self.number == 'phone' else self.recipient.mobile
        if number and number.startswith('+'):
            number = number[1:]
    
        log_vals = {
            'number': number,
            'user': self.env.user.id,
            'message': self.message,
            'config_id': self.config_id.id if self.config_id else False,
            'template_id': self.template_id.id if self.template_id else False,
            'attachment': self.attachment,
            'attachment_filename': self.attachment_filename,
            'partner_id': self.recipient.id if self.recipient else False,
        }
    
        if not self.config_id or not self.recipient:
            log_vals.update({'status': 'failed'})
            self.env['whatsapp.message.history'].create(log_vals)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Warning'),
                    'message': _('Configuration or recipient is missing.'),
                    'type': 'warning',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
    
        if self.config_id not in self.env.user.allowed_providers:
            raise UserError(_("Selected configuration is not allowed for this user."))
    
        media_id = None
        media_type = None
        file_data = None
        filename = None
        if self.attachment:
            try:
                media_id, media_type, file_data, filename = self._upload_media()
            except Exception as e: 
                _logger.error("Error uploading media: %s", str(e))
                media_id = None
    
        headers = {
            'Authorization': f'Bearer {self.config_id.access_token}',
            'Content-Type': 'application/json',
        }
        url = f"{self.config_id.api_url}/{self.config_id.instance_id}/messages"
    
        channel = self._get_or_create_chat_channel(self.recipient, self.config_id.id) 
    
        if self.template_id:
            any_attempt_made = True
            template_payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "template",
                "template": {
                    "name": self.template_id.name,
                    "language": {
                        "code": self.template_id.lang.code.replace('-', '_')
                    },
                    "components": []
                }
            }
            try:
                response = requests.post(url, headers=headers, json=template_payload)
                _logger.info("Template message response status: %s", response.status_code)
                _logger.info("Template message response text: %s", response.text)
                
                if response.status_code in [200, 201]:
                    try:
                        response_data = response.json()
                        _logger.info("Template message response data: %s", response_data)
                        messages = response_data.get('messages', [])
                        if messages:
                            at_least_one_success = True
                            message_id = messages[0].get('id')
                            _logger.info(message_id)
                            conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
                            log_vals.update({
                                'message_id': message_id,
                                'conversation_id': conversation_id,
                                'is_message_sent':True,
                            })
                        
                    except ValueError as e:
                        _logger.error("Failed to parse template response as JSON: %s", str(e))
                else:
                    _logger.error("WhatsApp API error for template message: %s", response.text)
            except Exception as e:
                _logger.error("Error sending template message: %s", str(e))
    
        if self.message and not self.template_id:
            any_attempt_made = True
            text_payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {
                    "body": self.message
                }
            }
            try:
                response = requests.post(url, headers=headers, json=text_payload)
                _logger.info("Text message response status: %s", response.status_code)
                _logger.info("Text message response text: %s", response.text)
                
                if response.status_code in [200, 201]:
                    try:
                        response_data = response.json()
                        _logger.info("Text message response data: %s", response_data)
                        messages = response_data.get('messages', [])
                        if messages:
                            at_least_one_success = True
                            message_id = messages[0].get('id')
                            _logger.info(message_id)
                            conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
                            log_vals.update({
                                'message_id': message_id,
                                'conversation_id': conversation_id,
                                'is_message_sent':True,
                            })
                            if channel:
                                message = self.env['mail.message'].sudo().create({
                                    'model': 'discuss.channel',
                                    'res_id': channel.id,
                                    'message_type': 'comment',
                                    'subtype_id': self.env.ref('mail.mt_comment').id,
                                    'body': self.message,
                                    'author_id': self.env.user.partner_id.id,
                                    'date': fields.Datetime.now(),
                                    'whatsapp_message_id': message_id,
                                }) 
                                
                    except ValueError as e:
                        _logger.error("Failed to parse text response as JSON: %s", str(e))
                else:
                    _logger.error("WhatsApp API error for text message: %s", response.text)
            except Exception as e:
                _logger.error("Error sending text message: %s", str(e))
    
        if media_id:
            any_attempt_made = True
            media_payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": media_type,
                media_type: {
                    "id": media_id
                }
            }
            try:
                response = requests.post(url, headers=headers, json=media_payload)
                _logger.info("Media message response status: %s", response.status_code)
                _logger.info("Media message response text: %s", response.text)
                
                if response.status_code in [200, 201]:
                    try:
                        response_data = response.json()
                        _logger.info("Media message response data: %s", response_data)
                        messages = response_data.get('messages', [])
                        if messages:
                            at_least_one_success = True
                            message_id = messages[0].get('id')
                            conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
                            log_vals.update({
                                'message_id': message_id,
                                'conversation_id': conversation_id,
                                'is_message_sent':True,
                            })
                            if channel:
                                attachment = self.env['ir.attachment'].sudo().create({
                                    'name': filename,
                                    'datas': base64.b64encode(file_data),
                                    'res_model': 'discuss.channel',
                                    'res_id': channel.id,
                                    'mimetype': {
                                        'image': 'image/jpeg' if filename.endswith(('.jpg', '.jpeg')) else 'image/png',
                                        'document': 'application/pdf',
                                        'video': 'video/mp4',
                                        'audio': 'audio/mp3',
                                    }.get(media_type, 'application/octet-stream'),
                                })
                                message = self.env['mail.message'].sudo().create({
                                    'model': 'discuss.channel',
                                    'res_id': channel.id,
                                    'message_type': 'comment',
                                    'subtype_id': self.env.ref('mail.mt_comment').id,
                                    'body': '',
                                    'author_id': self.env.user.partner_id.id,
                                    'date': fields.Datetime.now(),
                                    'whatsapp_message_id': message_id,
                                    'attachment_ids': [(4, attachment.id)],
                                }) 
                    except ValueError as e:
                        _logger.error("Failed to parse media response as JSON: %s", str(e))
                else:
                    _logger.error("WhatsApp API error for media message: %s", response.text)
            except Exception as e:
                _logger.error("Error sending media message: %s", str(e))
    
        if not any_attempt_made:
            log_vals.update({'status': 'failed'})
            self.env['whatsapp.message.history'].create(log_vals)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Warning'),
                    'message': _('No message, template, or media provided to send.'),
                    'type': 'warning',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
    
        log_vals.update({
            'status': 'sent' if at_least_one_success else 'failed',
        })
        history_record = self.env['whatsapp.message.history'].sudo().create(log_vals)
    
        notification_type = 'success' if at_least_one_success else 'warning'
        notification_message = (
            _('Message sent successfully to %s!') % self.recipient.name
            if at_least_one_success
            else _('Failed to send message to %s.') % self.recipient.name
        )
    
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success') if at_least_one_success else _('Warning'),
                'message': notification_message,
                'type': notification_type,
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


    
    def _get_or_create_chat_channel(self, partner, config_id=False):
        """
        Find or create a group discuss.channel for the given partner and all operators.
        """
        if not partner:
            _logger.error("No partner provided for channel creation")
            return False

        if config_id:
            config = self.env['whatsapp.config'].sudo().browse(config_id)
            if not config.exists():
                _logger.error("Configuration ID %s not found", config_id)
                return False
            if not config.operator_ids:
                _logger.warning("No operators defined in whatsapp.config ID %s", config_id)
                return False
            # Optional: Keep user check if needed for specific business logic
            if self.env.user not in config.operator_ids:
                _logger.error("User %s not in operator_ids for config %s", self.env.user.name, config_id)
                return False
        else:
            _logger.warning("No config_id provided; proceeding without operator validation")
            config = False

        try:
            # Get all operators from whatsapp.config.operator_ids if config exists
            operator_partners = config.operator_ids.mapped('partner_id') if config else [self.env.user.partner_id]
            _logger.info("Operators for config ID %s: %s", config_id or 'N/A', [p.name for p in operator_partners])

            # Search for an existing group channel with the partner
            domain = [
                ('channel_type', '=', 'group'),
                ('channel_member_ids.partner_id', 'in', [partner.id]),
            ]
            if config_id:
                domain.append(('whatsapp_config_id', '=', config_id))
            channel = self.env['discuss.channel'].sudo().search(domain, limit=1)

            if not channel:
                # Create a new group channel with all operators and the partner
                channel_vals = {
                    'name': f"WhatsApp Group - {partner.name}",
                    'channel_type': 'group',
                    'channel_member_ids': [
                        (0, 0, {'partner_id': op_partner.id}) for op_partner in operator_partners
                    ] + [(0, 0, {'partner_id': partner.id})],
                }
                if config_id:
                    channel_vals['whatsapp_config_id'] = config_id
                _logger.debug("Creating group channel with values: %s", channel_vals)
                channel = self.env['discuss.channel'].sudo().create(channel_vals)
                _logger.info("Created new group channel: %s (ID: %d)", channel.name, channel.id)
            else:
                # Ensure all operators are members of the existing channel
                current_member_partners = channel.channel_member_ids.mapped('partner_id')
                missing_partners = operator_partners - current_member_partners
                if missing_partners:
                    new_members = [(0, 0, {'partner_id': p.id}) for p in missing_partners]
                    _logger.debug("Adding missing members to group channel %s: %s", channel.id, missing_partners.mapped('name'))
                    channel.write({
                        'channel_member_ids': new_members
                    })
                    _logger.info("Added missing operators %s to group channel ID %s", missing_partners.mapped('name'), channel.id)

            _logger.info('Group channel created/found: %s (ID: %d, Members: %s)',
                         channel.name, channel.id, channel.channel_member_ids.mapped('partner_id.name'))
            return channel
        except Exception as e:
            _logger.error("Failed to create or update group channel for partner %s and config %s: %s",
                          partner.name, config_id or 'N/A', str(e))
            return False

class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_send_message(self):
        """Open the MessageConfiguration wizard to send a WhatsApp message."""
        self.ensure_one()
        model = self.env['ir.model'].search([('model','=','res.partner')])
         
        return {
            'type': 'ir.actions.act_window',
            'name': _('Write Message'),
            'res_model': 'message.configuration',
            'view_mode': 'form',
            'view_id': self.env.ref('meta_whatsapp_all_in_one.view_message_configuration_form').id,
            'target': 'new',   
            'context': {
                'default_recipient': self.id,
                'default_model': model.id
            },
        }