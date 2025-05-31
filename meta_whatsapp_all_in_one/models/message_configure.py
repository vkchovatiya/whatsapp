# -*- coding: utf-8 -*-
import base64
from odoo.exceptions import UserError
import requests
from odoo import models, fields, api
from odoo.tools import _
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
        string="Model",
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
        compute="compute_allowed_config_ids",
    )
    number = fields.Selection(
        [('phone', 'Phone'), ('mobile', 'Mobile')],
        string="Number",
        default='phone',
    )
    template_id = fields.Many2one(
        'whatsapp.template',
        string="Template",
        help="Select a template to populate the message field",
        domain="[('config_id', '=', config_id), ('status', '=', 'APPROVED'), '|', ('available', '=', False), ('available', '=', model)]"
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'message_configuration_ir_attachments_rel',
        'message_id', 'attachment_id',
        string="Attachments"
    )
    number_field = fields.Integer(
        string="Record Number",
        help="The ID of the record in the selected model to fetch template parameters from"
    )

    @api.depends('config_id')
    def compute_allowed_config_ids(self):
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

        if 'number_field' in fields_list and active_id and not res.get('number_field'):
            res['number_field'] = active_id  # Set the number_field to the active_id

        return res

    @api.onchange('config_id')
    def onchange_config_id(self):
        self.template_id = False
        return {
            'domain': {
                'template_id': [('config_id', '=', self.config_id.id), ('status', '=', 'APPROVED')],
                'config_id': [('id', 'in', self.env.user.allowed_providers.ids)]
            }
        }

    @api.onchange('template_id')
    def onchange_template_id(self):
        """
        Populate the message field with the calculated message after replacing template parameters.
        """
        if self.template_id:
            try:
                # Calculate the message with replaced parameters
                calculated_message, _ = self.get_calculated_message_and_parameters()
                self.message = calculated_message
            except Exception as e:
                _logger.error("Error calculating message for template %s: %s", self.template_id.name, str(e))
                self.message = self.template_id.message  # Fallback to raw message if calculation fails
                return {
                    'warning': {
                        'title': _('Warning'),
                        'message': _('Failed to calculate message with parameters: %s') % str(e),
                    }
                }
        else:
            self.message = False

    def get_calculated_message_and_parameters(self):
        """
        Calculate the message by replacing template parameters with field values and return the components for the API.
        Returns a tuple of (calculated_message, components).
        """
        if not self.template_id or not self.model:
            return self.template_id.message if self.template_id else False, []

        # Validate that the template is applicable to the current model
        if self.template_id.available and self.template_id.available.id != self.model.id:
            raise UserError(
                _('Template %s is not applicable to model %s. It applies to %s.') %
                (self.template_id.name, self.model.name, self.template_id.available.name)
            )

        # Fetch parameter mappings for the template
        mappings = self.env['whatsapp.template.parameter.mapping'].search([('template_id', '=', self.template_id.id)])
        if not mappings:
            return self.template_id.message, []  # No parameters to replace

        # Get the model name from ir.model
        model_name = self.model.model
        model_obj = self.env[model_name]

        # Fetch the record using the number_field (which is the ID of the record)
        if not self.number_field:
            raise UserError(_('Record number (ID) is missing for fetching template parameters.'))

        record = model_obj.search([('id', '=', self.number_field)], limit=1)
        if not record:
            raise UserError(_('No record found in model %s with ID %s.') % (model_name, self.number_field))

        # Get the raw message from the template
        calculated_message = self.template_id.message or ""
        body_parameters = []  # List to hold all parameters for the body component

        # Process each parameter mapping
        for mapping in mappings:
            field_name = mapping.field_id.name
            parameter_name = mapping.parameter_name

            # Fetch the field value from the record
            try:
                field_value = record[field_name]
                if isinstance(field_value, models.BaseModel):
                    # If the field is a related record, get a display name or ID
                    field_value = field_value.display_name or field_value.id
                elif field_value is None:
                    field_value = ''
                else:
                    field_value = str(field_value)
            except Exception as e:
                _logger.error("Error fetching field %s from model %s: %s", field_name, model_name, str(e))
                raise UserError(_('Error fetching field %s from model %s: %s') % (field_name, model_name, str(e)))

            # Replace the parameter in the message (e.g., {{1}} or {{field_name}})
            placeholder = f"{parameter_name}"  # Fixed placeholder format to match WhatsApp syntax
            calculated_message = calculated_message.replace(placeholder, field_value)

            # Add the parameter to the body parameters list
            body_parameters.append({
                "type": "text",
                "text": field_value
            })

        # Create a single body component with all parameters
        components = []
        if body_parameters:
            components.append({
                "type": "body",
                "parameters": body_parameters
            })

        return calculated_message, components

    def validate_media(self, attachment):
        """Validate attachment against WhatsApp's supported media types and size limits."""
        media_types = {
            'audio': {
                'mimetypes': ['audio/aac', 'audio/mp4', 'audio/mpeg', 'audio/amr', 'audio/ogg'],
                'size_limit_mb': 16,
            },
            'document': {
                'mimetypes': [
                    'text/plain', 'application/pdf', 'application/vnd.ms-powerpoint',
                    'application/msword', 'application/vnd.ms-excel',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                ],
                'size_limit_mb': 100,
            },
            'image': {
                'mimetypes': ['image/jpeg', 'image/png'],
                'size_limit_mb': 5,
            },
            'sticker': {
                'mimetypes': ['image/webp'],
                'size_limit_mb': 0.1,
            },
            'video': {
                'mimetypes': ['video/mp4', 'video/3gpp'],
                'size_limit_mb': 16,
            }
        }

        # Get file data and size
        file_data = base64.b64decode(attachment.datas)
        file_size_mb = len(file_data) / (1024 * 1024)
        mime_type = attachment.mimetype.lower()
        filename = attachment.name.lower()

        # Determine media type based on mimetype
        media_type = None
        for m_type, config in media_types.items():
            if mime_type in config['mimetypes']:
                media_type = m_type
                break

        if not media_type:
            supported_types = ', '.join([f"{k}: {', '.join(v['mimetypes'])}" for k, v in media_types.items()])
            raise UserError(_('Unsupported file type for %s. Supported types: %s') % (attachment.name, supported_types))

        # Validate size
        if file_size_mb > media_types[media_type]['size_limit_mb']:
            raise UserError(
                _('File %s exceeds WhatsApp size limit of %sMB for %s media.') %
                (attachment.name, media_types[media_type]['size_limit_mb'], media_type)
            )

        # Additional validation for specific types
        if media_type == 'audio' and mime_type == 'audio/ogg':
            _logger.warning(
                "Audio file %s is OGG format. Ensure it uses the opus codec, as base audio/ogg is not supported.",
                attachment.name)

        if media_type == 'video':
            _logger.warning(
                "Video file %s must use H.264 video codec and AAC audio codec with a single audio stream or no audio stream.",
                attachment.name)

        return media_type, file_data, mime_type, attachment.name

    def upload_media(self, attachment):
        """Upload a single media attachment to WhatsApp API and return media_id, media_type, file_data, filename."""
        if not attachment or not attachment.datas:
            return None, None, None, None

        try:
            media_type, file_data, mime_type, filename = self.validate_media(attachment)

            url = f"{self.config_id.api_url}/{self.config_id.instance_id}/media"
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
            }
            files = {
                'file': (filename, file_data, mime_type),
                'messaging_product': (None, 'whatsapp'),
                'type': (None, media_type),
            }
            response = requests.post(url, headers=headers, files=files)
            if response.status_code != 200:
                _logger.error("Failed to upload media %s: %s (Status: %s)", filename, response.text,
                              response.status_code)
                raise UserError(_('Failed to upload media %s to WhatsApp: %s') % (filename, response.text))

            response_data = response.json()
            media_id = response_data.get('id')
            if not media_id:
                _logger.error("Media ID not found in upload response for %s: %s", filename, response_data)
                raise UserError(_('Media ID not found in WhatsApp upload response for %s.') % filename)

            _logger.info("Successfully uploaded media %s to WhatsApp, media ID: %s", filename, media_id)
            return media_id, media_type, file_data, filename

        except Exception as e:
            _logger.error("Error uploading media %s: %s", attachment.name, str(e))
            raise UserError(_('Error uploading media %s to WhatsApp: %s') % (attachment.name, str(e)))

    def delete_media(self, media_id):
        """Delete a media file from WhatsApp API using the media ID."""
        try:
            phone_number_id = self.config_id.instance_id
            if not phone_number_id:
                _logger.error("Phone number ID not found in WhatsApp configuration ID %s", self.config_id.id)
                raise UserError(_('Phone number ID not found in WhatsApp configuration.'))

            url = f"{self.config_id.api_url}/{media_id}/?phone_number_id={phone_number_id}"
            headers = {
                'Authorization': f'Bearer {self.config_id.access_token}',
            }
            response = requests.delete(url, headers=headers)
            if response.status_code == 200:
                _logger.info("Successfully deleted media ID %s from WhatsApp", media_id)
            else:
                _logger.error("Failed to delete media ID %s: %s (Status: %s)", media_id, response.text,
                              response.status_code)
                raise UserError(_('Failed to delete media ID %s from WhatsApp: %s') % (media_id, response.text))
        except Exception as e:
            _logger.error("Error deleting media ID %s: %s", media_id, str(e))
            return False

    def action_send_message(self):
        self.ensure_one()
        at_least_one_success = False
        any_attempt_made = False

        number = self.recipient.phone if self.number == 'phone' else self.recipient.mobile
        if not number:
            raise UserError(_('Recipient phone number is missing.'))
        if number.startswith('+'):
            number = number[1:]

        log_vals = {
            'number': number,
            'user': self.env.user.id,
            'message': self.message,
            'config_id': self.config_id.id if self.config_id else False,
            'template_id': self.template_id.id if self.template_id else False,
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

        headers = {
            'Authorization': f'Bearer {self.config_id.access_token}',
            'Content-Type': 'application/json',
        }
        url = f"{self.config_id.api_url}/{self.config_id.instance_id}/messages"

        channel = self.get_or_create_chat_channel(self.recipient, self.config_id.id)

        if self.template_id:
            any_attempt_made = True

            value, components = self.get_calculated_message_and_parameters()
            if value:
                template_payload = {
                    "messaging_product": "whatsapp",
                    "to": number,
                    "type": "template",
                    "type": "text",
                    "text": {
                        "body": value
                    }
                }
            else:
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
            _logger.info(template_payload)
            try:
                response = requests.post(url, headers=headers, json=template_payload)
                _logger.info("Template message response status: %s", response.status_code)
                _logger.info("Template message response text: %s", response.text)

                if response.status_code in [200, 201]:
                    response_data = response.json()
                    _logger.info("Template message response data: %s", response_data)
                    messages = response_data.get('messages', [])
                    if messages:
                        at_least_one_success = True
                        message_id = messages[0].get('id')
                        _logger.info("Template message sent successfully, message ID: %s", message_id)
                        conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
                        log_vals.update({
                            'message_id': message_id,
                            'conversation_id': conversation_id,
                            'is_message_sent': True,
                        })
                    else:
                        _logger.error("No messages returned in template response: %s", response_data)
                        raise UserError(_('No message ID returned from WhatsApp API for template message.'))
                else:
                    _logger.error("WhatsApp API error for template message: %s (Status: %s)", response.text,
                                  response.status_code)
                    raise UserError(_('Failed to send template message: %s') % response.text)
            except Exception as e:
                _logger.error("Error sending template message: %s", str(e))
                log_vals.update({'status': 'failed'})
                self.env['whatsapp.message.history'].create(log_vals)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to send template message: %s') % str(e),
                        'type': 'danger',
                        'sticky': False,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }

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
                    response_data = response.json()
                    _logger.info("Text message response data: %s", response_data)
                    messages = response_data.get('messages', [])
                    if messages:
                        at_least_one_success = True
                        message_id = messages[0].get('id')
                        _logger.info("Text message sent successfully, message ID: %s", message_id)
                        conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
                        log_vals.update({
                            'message_id': message_id,
                            'conversation_id': conversation_id,
                            'is_message_sent': True,
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
                            _logger.info("Text message added to channel ID %s: %s", channel.id, message.id)
                    else:
                        _logger.error("No messages returned in text response: %s", response_data)
                        raise UserError(_('No message ID returned from WhatsApp API for text message.'))
                else:
                    _logger.error("WhatsApp API error for text message: %s (Status: %s)", response.text,
                                  response.status_code)
                    raise UserError(_('Failed to send text message: %s') % response.text)
            except Exception as e:
                _logger.error("Error sending text message: %s", str(e))
                log_vals.update({'status': 'failed'})
                self.env['whatsapp.message.history'].create(log_vals)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to send text message: %s') % str(e),
                        'type': 'danger',
                        'sticky': False,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }

        if self.attachment_ids:
            for attachment in self.attachment_ids:
                any_attempt_made = True
                media_id, media_type, file_data, filename = self.upload_media(attachment)
                if not media_id:
                    continue  # Skip if media upload failed

                media_payload = {
                    "messaging_product": "whatsapp",
                    "to": number,
                    "type": media_type,
                    media_type: {
                        "id": media_id,
                        "caption": self.message if self.message else ""
                    }
                }
                try:
                    response = requests.post(url, headers=headers, json=media_payload)
                    _logger.info("Media message response status for %s: %s", filename, response.status_code)
                    _logger.info("Media message response text for %s: %s", filename, response.text)

                    if response.status_code in [200, 201]:
                        response_data = response.json()
                        _logger.info("Media message response data for %s: %s", filename, response_data)
                        messages = response_data.get('messages', [])
                        if messages:
                            at_least_one_success = True
                            message_id = messages[0].get('id')
                            _logger.info("Media message sent successfully for %s, message ID: %s", filename, message_id)
                            conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
                            log_vals.update({
                                'message_id': message_id,
                                'conversation_id': conversation_id,
                                'is_message_sent': True,
                            })
                            if channel:
                                new_attachment = self.env['ir.attachment'].sudo().create({
                                    'name': filename,
                                    'datas': attachment.datas,
                                    'res_model': 'discuss.channel',
                                    'res_id': channel.id,
                                    'mimetype': attachment.mimetype,
                                })
                                message = self.env['mail.message'].sudo().create({
                                    'model': 'discuss.channel',
                                    'res_id': channel.id,
                                    'message_type': 'comment',
                                    'subtype_id': self.env.ref('mail.mt_comment').id,
                                    'body': self.message if self.message else '',
                                    'author_id': self.env.user.partner_id.id,
                                    'date': fields.Datetime.now(),
                                    'whatsapp_message_id': message_id,
                                    'attachment_ids': [(4, new_attachment.id)],
                                })
                                _logger.info("Media message with attachment %s added to channel ID %s: %s", filename,
                                             channel.id, message.id)
                            # Delete the media from WhatsApp after sending
                            self.delete_media(media_id)
                        else:
                            _logger.error("No messages returned in media response for %s: %s", filename, response_data)
                            raise UserError(
                                _('No message ID returned from WhatsApp API for media message %s.') % filename)
                    else:
                        _logger.error("WhatsApp API error for media message %s: %s (Status: %s)", filename,
                                      response.text, response.status_code)
                        raise UserError(_('Failed to send media message %s: %s') % (filename, response.text))
                except Exception as e:
                    _logger.error("Error sending media message for %s: %s", filename, str(e))
                    log_vals.update({'status': 'failed'})
                    self.env['whatsapp.message.history'].create(log_vals)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Error'),
                            'message': _('Failed to send media message %s: %s') % (filename, str(e)),
                            'type': 'danger',
                            'sticky': False,
                            'next': {'type': 'ir.actions.act_window_close'},
                        }
                    }

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
        if at_least_one_success:
            notification_message = _('Message sent successfully to %s!') % self.recipient.name
        else:
            notification_message = _('Failed to send message to %s.') % self.recipient.name

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

    def get_or_create_chat_channel(self, partner, config_id=False):
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
            if self.env.user not in config.operator_ids:
                _logger.error("User %s not in operator_ids for config %s", self.env.user.name, config_id)
                return False
        else:
            _logger.warning("No config_id provided; proceeding without operator validation")
            config = False

        try:
            operator_partners = config.operator_ids.mapped('partner_id') if config else [self.env.user.partner_id]
            _logger.info("Operators for config ID %s: %s", config_id or 'N/A', [p.name for p in operator_partners])

            domain = [
                ('channel_type', '=', 'group'),
                ('channel_member_ids.partner_id', 'in', [partner.id]),
            ]
            if config_id:
                domain.append(('whatsapp_config_id', '=', config_id))
            channel = self.env['discuss.channel'].sudo().search(domain, limit=1)

            if not channel:
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
                current_member_partners = channel.channel_member_ids.mapped('partner_id')
                missing_partners = operator_partners - current_member_partners
                if missing_partners:
                    new_members = [(0, 0, {'partner_id': p.id}) for p in missing_partners]
                    _logger.debug("Adding missing members to group channel %s: %s", channel.id,
                                  missing_partners.mapped('name'))
                    channel.write({
                        'channel_member_ids': new_members
                    })
                    _logger.info("Added missing operators %s to group channel ID %s", missing_partners.mapped('name'),
                                 channel.id)

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
        model = self.env['ir.model'].search([('model', '=', 'res.partner')])
        _logger.info('Opening message configuration wizard for partner %s', self.name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Write Message'),
            'res_model': 'message.configuration',
            'view_mode': 'form',
            'view_id': self.env.ref('meta_whatsapp_all_in_one.view_message_configuration_form').id,
            'target': 'new',
            'context': {
                'default_recipient': self.id,
                'default_model': model.id,
                'default_number_field': self.id,  # Pass the partner ID as the number_field
            },
        }