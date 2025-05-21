import json
import hmac
import hashlib
from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
import logging
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime

_logger = logging.getLogger(__name__)


class WhatsAppWebhook(http.Controller):
    """
    Controller to handle Meta WhatsApp Business API webhook requests.
    Supports verification requests (GET) and event notifications (POST).
    """

    @http.route('/whatsapp/webhook/<int:config_id>', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def whatsapp_webhook(self, config_id, **kwargs):
        """
        Handle WhatsApp webhook requests from Meta.
        - GET: Verify the webhook endpoint.
        - POST: Process incoming message notifications.
        """
        # Fetch the configuration record
        config = request.env['whatsapp.config'].sudo().browse(config_id)
        if not config.exists():
            _logger.error("WhatsApp configuration ID %s not found.", config_id)
            return json.dumps({'error': 'Invalid configuration'}, status=404)

        if request.httprequest.method == 'GET':
            return self._handle_verification_request(config, kwargs)
        elif request.httprequest.method == 'POST':
            return self._handle_event_notification(config)

    def _handle_verification_request(self, config, kwargs):
        """
        Handle webhook verification requests (GET) from Meta.
        Validate the verify_token and return the challenge.
        """
        try:
            mode = kwargs.get('hub.mode')
            challenge = kwargs.get('hub.challenge')
            verify_token = kwargs.get('hub.verify_token')

            if not (mode and challenge and verify_token):
                _logger.error("Missing verification parameters: mode=%s, challenge=%s, verify_token=%s",
                              mode, challenge, verify_token)
                return json.dumps({'error': 'Missing parameters'})

            if mode != 'subscribe':
                _logger.error("Invalid mode: %s", mode)
                return json.dumps({'error': 'Invalid mode'})

            if verify_token != config.webhook_token:
                _logger.error("Invalid verify token for config ID %s", config.id)
                return json.dumps({'error': 'Invalid verify token'})

            _logger.info("Webhook verification successful for config ID %s", config.id)
            return challenge
        except Exception as e:
            _logger.error("Error in webhook verification: %s", str(e))
            return json.dumps({'error': str(e)})

    def _handle_event_notification(self, config):
        """
        Handle event notifications (POST) from Meta, such as incoming WhatsApp messages.
        Validate payload signature and process the message.
        """
        try:
            # Read the raw payload
            payload = request.httprequest.data
            if not payload:
                _logger.error("Empty payload received for config ID %s", config.id)
                return json.dumps({'error': 'Empty payload'}, status=400)

            # Parse JSON payload
            data = json.loads(payload.decode('utf-8'))
            _logger.info("Received webhook payload for config ID %s: %s", config.id, data)

            self._process_whatsapp_notification(config, data)

            # Respond with 200 OK
            return json.dumps({'status': 'received'})
        except json.JSONDecodeError:
            _logger.error("Invalid JSON payload for config ID %s", config.id)
            return json.dumps({'error': 'Invalid JSON'})
        except Exception as e:
            _logger.error("Error processing webhook notification: %s", str(e))
            return json.dumps({'error': str(e)})

    def _process_whatsapp_notification(self, config, data):

        entries = data.get('entry', [])
        for entry in entries:
            changes = entry.get('changes', [])
            for change in changes:
                if change.get('field') == 'messages':
                    value = change.get('value', {})

                    messages = value.get('messages', [])
                    contacts = value.get('contacts', [])
                    for message in messages:
                        from_number = message.get('from')
                        message_type = message.get('type')
                        message_content = message.get(message_type, {}).get(
                            'body') if message_type == 'text' else f"[{message_type} message]"
                        message_id = message.get('id')
                        timestamp = message.get('timestamp')
                        context = message.get('context', {})
                        reply_to_message_id = context.get('id')

                        try:
                            message_datetime = datetime.fromtimestamp(int(timestamp))
                        except (ValueError, TypeError):
                            message_datetime = fields.Datetime.now()

                        partner = self._find_or_create_partner(from_number, contacts)
                        authorized_users = request.env['res.users'].sudo().search([
                            '|',
                            ('allowed_providers', 'in', [config.id]),
                            ('default_provider', '=', config.id),
                        ], limit=1)
                        _logger.info(authorized_users)
                        create_vals = {
                            'number': from_number,
                            'partner_id': partner.id if partner else False,
                            'config_id': config.id,
                            'message_id': message_id,
                            'message': message_content,
                            'status': 'received',
                            'send_date': message_datetime,
                            'user': authorized_users.id,
                            'received_date': message_datetime,
                        }
                        if reply_to_message_id:
                            create_vals['reply_to_message_id'] = reply_to_message_id
                        history_record = request.env['whatsapp.message.history'].sudo().create(create_vals)

                        if partner:
                            channel = self._get_or_create_chat_channel(partner, config.id)
                            if channel:
                                message_vals = {
                                    'model': 'discuss.channel',
                                    'res_id': channel.id,
                                    'message_type': 'comment',
                                    'subtype_id': request.env.ref('mail.mt_comment').id,
                                    'body': message_content,
                                    'author_id': partner.id,
                                    'date': message_datetime,
                                    'whatsapp_message_id': message_id,
                                }
                                if reply_to_message_id:
                                    parent_message = request.env['mail.message'].sudo().search([
                                        ('whatsapp_message_id', '=', reply_to_message_id),
                                        ('model', '=', 'discuss.channel'),
                                        ('res_id', '=', channel.id),
                                    ], limit=1)
                                    if parent_message:
                                        message_vals['parent_id'] = parent_message.id
                                mes = request.env['mail.message'].sudo().create(message_vals)
                                _logger.info(mes)

                    statuses = value.get('statuses', [])
                    for status_update in statuses:
                        message_id = status_update.get('id')
                        status = status_update.get('status')
                        recipient_number = status_update.get('recipient_id')
                        timestamp = status_update.get('timestamp')
                        conversation_id = status_update.get('conversation', {}).get('id')

                        try:
                            status_datetime = datetime.fromtimestamp(int(timestamp))
                        except (ValueError, TypeError):
                            status_datetime = fields.Datetime.now()

                        valid_statuses = ['sent', 'delivered', 'read', 'failed']
                        model_status = status if status in valid_statuses else 'failed'

                        history_record = request.env['whatsapp.message.history'].sudo().search([
                            ('message_id', '=', message_id),
                            ('config_id', '=', config.id),
                        ], limit=1)
                        _logger.info(history_record)

                        if history_record:
                            update_vals = {
                                'status': model_status,
                                'send_date': status_datetime,
                            }
                            if model_status == 'delivered' and conversation_id:
                                update_vals['conversation_id'] = conversation_id
                            history_record.write(update_vals)
                        else:
                            partner = self._find_or_create_partner(recipient_number, contacts)
                            authorized_users = request.env['res.users'].sudo().search([
                                '|',
                                ('allowed_providers', 'in', [config.id]),
                                ('default_provider', '=', config.id),
                            ], limit=1)
                            _logger.info(authorized_users)
                            create_vals = {
                                'number': recipient_number,
                                'partner_id': partner.id if partner else False,
                                'config_id': config.id,
                                'user': authorized_users.id,
                                'message_id': message_id,
                                'status': model_status,
                                'send_date': status_datetime,
                            }
                            if model_status == 'delivered' and conversation_id:
                                create_vals['conversation_id'] = conversation_id
                            request.env['whatsapp.message.history'].sudo().create(create_vals)

    def _get_or_create_chat_channel(self, partner, config_id=False):
        """
        Find or create a direct message discuss.channel for the given partner.
        """
        if not partner:
            return False
        authorized_users = request.env['res.users'].sudo().search([
            '|',
            ('allowed_providers', 'in', [config_id]),
            ('default_provider', '=', config_id),
        ], limit=1)
        channel = request.env['discuss.channel'].sudo().search([
            ('channel_type', '=', 'chat'),
            ('whatsapp_config_id', '=', config_id),
            ('channel_member_ids.partner_id', 'in', [authorized_users.partner_id.id]),
            ('channel_member_ids.partner_id', 'in', [partner.id]),
        ], limit=1)

        if not channel:
            channel_vals = {
                'name': f"{authorized_users.name} - {partner.name}",
                'channel_type': 'chat',
                'channel_member_ids': [
                    (0, 0, {'partner_id': authorized_users.partner_id.id}),
                    (0, 0, {'partner_id': partner.id}),
                ],
                'whatsapp_config_id': config_id,
            }
            channel = request.env['discuss.channel'].sudo().create(channel_vals)

        _logger.info('Channel created/found: %s (ID: %d, Members: %s)',
                     channel.name, channel.id, channel.channel_member_ids.mapped('partner_id.name'))
        return channel

    def _find_or_create_partner(self, phone_number, contacts):
        """
        Find or create a res.partner record based on the phone number using a raw SQL query.
        """
        # normalized_mobile = request.env['res.partner'].sudo().normalize_phone_number(partner.normalized_mobile)
        # normalized_phone = request.env['res.partner'].sudo().normalize_phone_number(partner.normalized_phone)
        received_normalize = request.env['res.partner'].sudo().normalize_phone_number(phone_number)
        # _logger.info(normalized_mobile)
        # _logger.info(normalized_phone)
        _logger.info(received_normalize)
        # Use raw SQL query to search for a partner where mobile or phone matches the phone_number
        request.env.cr.execute("""
            SELECT id
            FROM res_partner
            WHERE normalized_mobile ILIKE %s OR normalized_phone ILIKE %s
            LIMIT 1
        """, (received_normalize, received_normalize))

        # Fetch the result
        partner_id = request.env.cr.fetchone()
        partner = None

        if partner_id:
            # If a partner is found, load the record
            partner = request.env['res.partner'].sudo().browse(partner_id[0])
        else:
            # If no partner is found, create a new one
            contact = contacts[0] if contacts else {}
            partner = request.env['res.partner'].sudo().create({
                'name': contact.get('profile', {}).get('name', phone_number),
                'phone': phone_number,
                'mobile': phone_number,
            })

        return partner