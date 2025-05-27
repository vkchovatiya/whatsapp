# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging
from odoo.addons.meta_whatsapp_all_in_one.controller.main_controller import WhatsAppWebhook
import requests
import json
from odoo import fields
import datetime

_logger = logging.getLogger(__name__)

class MyInviteController(WhatsAppWebhook):

    def _process_whatsapp_notification(self, config, data):
        """
        Process incoming WhatsApp messages and trigger a chatbot script.
        Executes a script only if the incoming message matches the script's message field.
        Handles both text and button message types.
        Updates existing history record instead of creating a duplicate.
        Checks if a chatbot is selected in res.config.settings and matches the incoming config.
        """
        _logger.info("Starting _process_whatsapp_notification for config ID %s with data: %s", config.id, data)
 
        company = request.env.company
        selected_chatbot = company.cr_chatbot_id
        if not selected_chatbot:
            _logger.info("No chatbot selected in company settings for company ID %s. Processing without chatbot.", company.id)
            super()._process_whatsapp_notification(config, data, create_channel_message=True)
            return
 
        chatbot_config = request.env['chatbot.configuration'].sudo().search([
            ('config_id', '=', config.id)
        ], limit=1)
        if not chatbot_config or chatbot_config.id != selected_chatbot.id:
            _logger.info(
                "Chatbot configuration mismatch: incoming config ID %s (chatbot ID %s) does not match selected chatbot ID %s in company settings.",
                config.id, chatbot_config.id if chatbot_config else 'None', selected_chatbot.id
            )
            super()._process_whatsapp_notification(config, data, create_channel_message=True)
            return

        _logger.info("Chatbot configuration matches: proceeding with chatbot processing for chatbot ID %s", selected_chatbot.id)
        # Call parent method but disable channel message creation
        super()._process_whatsapp_notification(config, data, create_channel_message=False)

        entries = data.get('entry', [])
        _logger.debug("Processing %d entries from webhook data", len(entries))
        chatbot_triggered = False
        partner = None
        channel = None
        message_content = None
        from_number = None
        message_id = None
        message_datetime = None
        history_record = None
        incoming_message_vals = None

        for entry in entries:
            changes = entry.get('changes', [])
            _logger.debug("Processing %d changes in entry", len(changes))
            for change in changes:
                if change.get('field') != 'messages':
                    _logger.debug("Skipping change with field %s; only processing messages", change.get('field'))
                    continue
                value = change.get('value', {})
                messages = value.get('messages', [])
                contacts = value.get('contacts', [])
                _logger.debug("Found %d messages and %d contacts in change value", len(messages), len(contacts))

                for message in messages:
                    from_number = message.get('from')
                    message_type = message.get('type')
                    message_id = message.get('id')
                    timestamp = message.get('timestamp')
                    _logger.info("Processing message from %s, type: %s, ID: %s, timestamp: %s", from_number, message_type, message_id, timestamp)
                    context = message.get('context', {})
                    reply_to_message_id = context.get('id')
                    _logger.info("Processing message from %s, type: %s, ID: %s, timestamp: %s, reply_to: %s", 
                                 from_number, message_type, message_id, timestamp, reply_to_message_id)

                    try:
                        message_datetime = datetime.datetime.fromtimestamp(int(timestamp))
                        message_datetime = fields.Datetime.to_string(message_datetime)
                        _logger.debug("Converted timestamp %s to datetime: %s", timestamp, message_datetime)
                    except (ValueError, TypeError) as e:
                        _logger.warning("Failed to convert timestamp %s to datetime: %s. Using current time.", timestamp, str(e))
                        message_datetime = fields.Datetime.now()
                        _logger.debug("Set message_datetime to current time: %s", message_datetime)

                    if message_type == 'text':
                        message_content = message.get('text', {}).get('body', '')
                        _logger.debug("Message type is text, content: %s", message_content)
                    elif message_type == 'button':
                        message_content = message.get('button', {}).get('text', '')
                        _logger.debug("Message type is button, content: %s", message_content)
                     

                    history_record = request.env['whatsapp.message.history'].sudo().search([
                        ('message_id', '=', message_id),
                        ('config_id', '=', config.id),
                    ], limit=1) 
                    if not history_record:
                        _logger.error("History record not found for message ID %s and config ID %s", message_id, config.id)
                        continue
                    _logger.debug("Found history record with ID %s for message ID %s", history_record.id, message_id)

                    chatbot_config = request.env['chatbot.configuration'].sudo().search([
                        ('config_id', '=', config.id)
                    ], limit=1)
                    if not chatbot_config:
                        _logger.info("No chatbot configuration found for config ID %s", config.id)
                        continue
                    _logger.debug("Found chatbot configuration with ID %s for config ID %s", chatbot_config.id, config.id)

                    partner = self._find_or_create_partner(from_number, contacts)
                    if not partner:
                        _logger.error("Could not find or create partner for number: %s", from_number)
                        continue
                    _logger.info("Partner found/created with ID %s and name %s for number %s", partner.id, partner.name, from_number)

                    channel = self._get_or_create_chat_channel(partner, config.id)
                    if not channel:
                        _logger.error("Could not find or create chat channel for partner: %s (ID: %s)", partner.name, partner.id)
                        continue
                    _logger.info("Chat channel found/created with ID %s and name %s", channel.id, channel.name)

                    incoming_message_vals = {
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
                            incoming_message_vals['parent_id'] = parent_message.id
                            _logger.info("Linked reply message ID %s to parent message ID %s", message_id, parent_message.id)
                        else:
                            _logger.warning("Parent message not found for reply_to_message_id %s in channel ID %s", reply_to_message_id, channel.id)


                    current_script = False
                    if message_content:
                        matching_scripts = request.env['chatbot.script'].sudo().search([
                            ('configuration_id', '=', chatbot_config.id),
                            ('message', 'ilike', message_content.lower()),
                        ], order='sequence ASC', limit=1)
                        if matching_scripts:
                            current_script = matching_scripts[0]
                            _logger.info("Found script with ID %s and sequence %s matching message '%s'", current_script.id, current_script.sequence, message_content)
                        else:
                            _logger.info("No script found with message matching '%s'", message_content)
                    else:
                        _logger.warning("Message content is empty; skipping script matching")

                    if current_script:
                        _logger.info("Chatbot triggered with script ID %s for message: %s", current_script.id, message_content)
                        chatbot_triggered = True
                        self._execute_chatbot_script(
                            current_script, partner, channel, config, message_id, message_datetime,
                            incoming_message_vals=incoming_message_vals
                        )
                        history_record.write({
                            'chatbot_id': chatbot_config.id,
                            'current_script_id': current_script.id,
                        })
                        _logger.debug("Updated history record ID %s with chatbot_id %s and current_script_id %s", history_record.id, chatbot_config.id, current_script.id)
                        break
                    else:
                        _logger.info("No script triggered for message: %s", message_content)
                        if incoming_message_vals:
                            request.env['mail.message'].sudo().create(incoming_message_vals)
                            _logger.info("No chatbot triggered; sent incoming message to channel ID %s", channel.id)

        _logger.info("Finished _process_whatsapp_notification for config ID %s, chatbot_triggered: %s", config.id, chatbot_triggered)

    def _execute_chatbot_script(self, script, partner, channel, config, incoming_message_id, message_datetime, incoming_message_vals=None):
        """
        Execute the chatbot script step (message, template, interactive, or action) and send the response.
        Add the response to the discuss.channel and update the conversation state.
        Only sends messages to the channel after actions are performed (if applicable).
        """
        _logger.info("Executing chatbot script ID %s with step_type: %s", script.id, script.step_type)

        # Flags to track if operators were added
        operators_added = False
        action_result_message = None

        if script.step_type == 'message':
            _logger.debug("Sending text message for script ID %s with response: %s", script.id, script.response)
            action_result_message = script.response
            self._send_chatbot_message(script.response, partner, channel, config, incoming_message_id, message_datetime, script, incoming_message_vals)

        elif script.step_type == 'template':
            if script.template_id:
                _logger.debug("Sending template message for script ID %s with template ID %s", script.id, script.template_id.id)
                action_result_message = f"Template: {script.template_id.name}"
                self._send_chatbot_template(script.template_id, partner, channel, config, incoming_message_id, message_datetime, script, incoming_message_vals)
            else:
                _logger.warning("No template_id defined for script ID %s with step_type 'template'", script.id)

        elif script.step_type == 'interactive':
            if script.template_id or script.response or script.action_id:
                _logger.debug("Sending interactive message for script ID %s", script.id)
                self._send_chatbot_interactive(script, partner, channel, config, incoming_message_id, message_datetime, incoming_message_vals)
            else:
                _logger.error("No template_id, response, or action defined for script ID %s with step_type 'interactive'", script.id)

        elif script.step_type == 'action':
            if script.action_id:
                _logger.debug("Executing action for script ID %s with action ID %s", script.id, script.action_id.id)
                operators_added, action_result = self._execute_chatbot_action(script.action_id, partner, channel, config,script)
                if action_result:
                    _logger.debug("Action result: %s", action_result)
                    action_result_message = action_result
                    self._send_chatbot_message(action_result, partner, channel, config, incoming_message_id, message_datetime, script, incoming_message_vals, operators_added)
            else:
                _logger.warning("No action_id defined for script ID %s with step_type 'action'", script.id)
        else:
            _logger.error("Unsupported step_type '%s' for script ID %s", script.step_type, script.id)

        # If no operators were added (not an action step or action not on res.users), send messages immediately
        if not operators_added and incoming_message_vals and action_result_message:
            _logger.info("No operators added; sending messages to channel ID %s immediately", channel.id)
            # Send incoming message
            incoming_message = request.env['mail.message'].sudo().create(incoming_message_vals)
            _logger.info("Sent incoming message ID %s to channel ID %s", incoming_message.id, channel.id)

            # Send chatbot response as a transient message
            message_vals = {
                'model': 'discuss.channel',
                'res_id': channel.id,
                'message_type': 'comment',
                'subtype_id': request.env.ref('mail.mt_comment').id,
                'body': action_result_message,
                'author_id': request.env.user.partner_id.id,
                'date': fields.Datetime.now(),
                'whatsapp_message_id': incoming_message_id,
            }
            message = request.env['mail.message'].sudo().create(message_vals)
            _logger.info("Sent chatbot response message ID %s to channel ID %s", message.id, channel.id)

    def _send_chatbot_interactive(self, script, partner, channel, config, reply_to_message_id, message_datetime, incoming_message_vals=None):
        """
        Send an interactive message (buttons or list) as part of the chatbot flow, add it to the discuss.channel,
        and update the conversation state.
        """
        _logger.info("Sending interactive message for script ID %s to partner ID %s on channel ID %s", script.id, partner.id, channel.id)
        number = partner.phone or partner.mobile
        if number and number.startswith('+'):
            number = number[1:]
        _logger.debug("Formatted phone number: %s", number)

        headers = {
            'Authorization': f'Bearer {config.access_token}',
            'Content-Type': 'application/json',
        }
        url = f"{config.api_url}/{config.instance_id}/messages"
        _logger.debug("Sending request to URL: %s with headers: %s", url, headers)

        # Determine the type of interactive message
        if script.template_id:
            _logger.debug("Template ID %s provided; sending as a template message instead of interactive", script.template_id.id)
            self._send_chatbot_template(script.template_id, partner, channel, config, reply_to_message_id, message_datetime, script, incoming_message_vals)
            return
        elif script.response:
            _logger.debug("Response %s provided; sending as a text message", script.response)
            self._send_chatbot_message(script.response, partner, channel, config, reply_to_message_id, message_datetime, script, incoming_message_vals)
            return
        elif script.action_id:
            _logger.debug("Step type is action for script ID %s; executing action ID %s", script.id, script.action_id.id)
            operators_added, action_result = self._execute_chatbot_action(script.action_id, partner, channel, config,script)
            if action_result:
                _logger.debug("Action result: %s", action_result)
                self._send_chatbot_message(action_result, partner, channel, config, reply_to_message_id, message_datetime, script, incoming_message_vals, operators_added)
            else:
                _logger.warning("Action ID %s returned no result for script ID %s", script.action_id.id, script.id)
            return
        else:
            _logger.error("Cannot send interactive message for script ID %s: no template_id, response, or action defined", script.id)
            return

    def _send_chatbot_message(self, message_content, partner, channel, config, reply_to_message_id, message_datetime, script, incoming_message_vals=None, operators_added=False):
        """
        Send a text message as part of the chatbot flow, add it to the discuss.channel,
        and update the conversation state.
        Only sends to channel if operators_added is True or no action is involved.
        """
        _logger.info("Sending chatbot message to partner ID %s on channel ID %s", partner.id, channel.id)
        number = partner.phone or partner.mobile
        if number and number.startswith('+'):
            number = number[1:]
        _logger.debug("Formatted phone number: %s", number)

        headers = {
            'Authorization': f'Bearer {config.access_token}',
            'Content-Type': 'application/json',
        }
        url = f"{config.api_url}/{config.instance_id}/messages"
        _logger.debug("Sending request to URL: %s with headers: %s", url, headers)

        payload = {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": message_content
            }
        }
        _logger.debug("Request payload: %s", payload)

        try:
            response = requests.post(url, headers=headers, json=payload)
            _logger.info("Chatbot text message response status: %s", response.status_code)
            _logger.debug("Chatbot text message response text: %s", response.text)

            if response.status_code in [200, 201]:
                response_data = response.json()
                messages = response_data.get('messages', [])
                if messages:
                    message_id = messages[0].get('id')
                    conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
                    _logger.debug("Message sent successfully, message ID: %s, conversation ID: %s", message_id, conversation_id)

                    authorized_users = request.env['res.users'].sudo().search([
                        '|',
                        ('allowed_providers', 'in', [config.id]),
                        ('default_provider', '=', config.id),
                    ], limit=1)
                    _logger.debug("Found authorized user with ID %s", authorized_users.id if authorized_users else 'None')
                    chatbot_config = request.env['chatbot.configuration'].sudo().search([
                        ('config_id', '=', config.id)
                    ], limit=1)
                    create_vals = {
                        'number': number,
                        'partner_id': partner.id,
                        'config_id': config.id,
                        'message_id': message_id,
                        'message': message_content,
                        'status': 'sent',
                        'send_date': fields.Datetime.now(),
                        'user': authorized_users.id if authorized_users else False,
                        'received_date': fields.Datetime.now(),
                        'conversation_id': conversation_id,
                        'reply_to_message_id': reply_to_message_id,
                        'chatbot_id': chatbot_config.id if chatbot_config else False,
                        'current_script_id': script.id,
                    }
                    history_record = request.env['whatsapp.message.history'].sudo().create(create_vals)
                    _logger.info("Created history record ID %s for sent message", history_record.id)

                    # Only send messages to the channel if operators were added or no action is involved
                    if operators_added or script.step_type != 'action':
                        if incoming_message_vals:
                            incoming_message = request.env['mail.message'].sudo().create(incoming_message_vals)
                            _logger.info("Sent incoming message ID %s to channel ID %s", incoming_message.id, channel.id)

                        message_vals = {
                            'model': 'discuss.channel',
                            'res_id': channel.id,
                            'message_type': 'comment',
                            'subtype_id': request.env.ref('mail.mt_comment').id,
                            'body': message_content,
                            'author_id': authorized_users.partner_id.id if authorized_users else request.env.user.partner_id.id,
                            'date': fields.Datetime.now(),
                            'whatsapp_message_id': message_id,
                        }
                        message = request.env['mail.message'].sudo().create(message_vals)
                        _logger.info("Sent chatbot response message ID %s to channel ID %s", message.id, channel.id)

                        # If operators were added, send the "Now you are talking with..." message
                        if operators_added:
                            company = request.env.company
                            welcome_message = f"Now you are talking with the user of {company.name}."
                            welcome_vals = {
                                'model': 'discuss.channel',
                                'res_id': channel.id,
                                'message_type': 'comment',
                                'subtype_id': request.env.ref('mail.mt_comment').id,
                                'body': welcome_message,
                                'author_id': authorized_users.partner_id.id if authorized_users else request.env.user.partner_id.id,
                                'date': fields.Datetime.now(),
                            }
                            welcome_message_record = request.env['mail.message'].sudo().create(welcome_vals)
                            _logger.info("Sent welcome message ID %s to channel ID %s: %s", welcome_message_record.id, channel.id, welcome_message)
                else:
                    _logger.error("No messages returned in response: %s", response_data)
            else:
                _logger.error("Failed to send message, status code: %s, response: %s", response.status_code, response.text)
        except Exception as e:
            _logger.error("Error sending chatbot message: %s", str(e))

    def _send_chatbot_template(self, template, partner, channel, config, reply_to_message_id, message_datetime, script, incoming_message_vals=None):
        """
        Send a template message as part of the chatbot flow, add it to the discuss.channel,
        and update the conversation state.
        """
        _logger.info("Sending chatbot template message with template ID %s to partner ID %s on channel ID %s", template.id, partner.id, channel.id)
        number = partner.phone or partner.mobile
        if number and number.startswith('+'):
            number = number[1:]
        _logger.debug("Formatted phone number: %s", number)

        headers = {
            'Authorization': f'Bearer {config.access_token}',
            'Content-Type': 'application/json',
        }
        url = f"{config.api_url}/{config.instance_id}/messages"
        _logger.debug("Sending request to URL: %s with headers: %s", url, headers)

        payload = {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "template",
            "template": {
                "name": template.name,
                "language": {
                    "code": template.lang.code.replace('-', '_')
                },
                "components": []
            }
        }
        _logger.debug("Request payload: %s", payload)

        try:
            response = requests.post(url, headers=headers, json=payload)
            _logger.info("Chatbot template message response status: %s", response.status_code)
            _logger.debug("Chatbot template message response text: %s", response.text)

            if response.status_code in [200, 201]:
                response_data = response.json()
                messages = response_data.get('messages', [])
                if messages:
                    message_id = messages[0].get('id')
                    conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
                    _logger.debug("Template message sent successfully, message ID: %s, conversation ID: %s", message_id, conversation_id)

                    authorized_users = request.env['res.users'].sudo().search([
                        '|',
                        ('allowed_providers', 'in', [config.id]),
                        ('default_provider', '=', config.id),
                    ], limit=1)
                    _logger.debug("Found authorized user with ID %s", authorized_users.id if authorized_users else 'None')
                    chatbot_config = request.env['chatbot.configuration'].sudo().search([
                        ('config_id', '=', config.id)
                    ], limit=1)
                    create_vals = {
                        'number': number,
                        'partner_id': partner.id,
                        'config_id': config.id,
                        'message_id': message_id,
                        'message': f"{template.message}",
                        'status': 'sent',
                        'send_date': fields.Datetime.now(),
                        'user': authorized_users.id if authorized_users else False,
                        'received_date': fields.Datetime.now(),
                        'conversation_id': conversation_id,
                        'reply_to_message_id': reply_to_message_id,
                        'template_id': template.id,
                        'chatbot_id': chatbot_config.id if chatbot_config else False,
                        'current_script_id': script.id,
                    }
                    history_record = request.env['whatsapp.message.history'].sudo().create(create_vals)
                    _logger.info("Created history record ID %s for sent template message", history_record.id)

                    # Send messages to the channel (template steps are not actions, so send immediately)
                    if incoming_message_vals:
                        incoming_message = request.env['mail.message'].sudo().create(incoming_message_vals)
                        _logger.info("Sent incoming message ID %s to channel ID %s", incoming_message.id, channel.id)

                    message_vals = {
                        'model': 'discuss.channel',
                        'res_id': channel.id,
                        'message_type': 'comment',
                        'subtype_id': request.env.ref('mail.mt_comment').id,
                        'body': template.message,
                        'author_id': authorized_users.partner_id.id if authorized_users else request.env.user.partner_id.id,
                        'date': fields.Datetime.now(),
                        'whatsapp_message_id': message_id,
                    }
                    message = request.env['mail.message'].sudo().create(message_vals)
                    _logger.info("Sent chatbot template response message ID %s to channel ID %s", message.id, channel.id)
                else:
                    _logger.error("No messages returned in response: %s", response_data)
            else:
                _logger.error("Failed to send template message, status code: %s, response: %s", response.status_code, response.text)
        except Exception as e:
            _logger.error("Error sending chatbot template: %s", str(e))

    def _execute_chatbot_action(self, action, partner, channel, config,script):
        """
        Execute a chatbot action by creating a new record in the specified model linked to the partner.
        If the model is res.users, add operators from chatbot.configuration to the channel.
        Returns a tuple (operators_added, result_message).
        """
        operators_added = False
        result_message = None

        if action.binding_id:
            model = request.env[action.binding_id.model]
            try: 
                _logger.info(action.binding_id.model)
                if action.binding_id.model == 'res.users':
                    chatbot_config = request.env['chatbot.configuration'].sudo().search([
                        ('config_id', '=', config.id)
                    ], limit=1)
                    if chatbot_config and chatbot_config.operator_ids:
                        operator_partners = chatbot_config.operator_ids.mapped('partner_id')
                        if operator_partners:
                            channel.sudo().write({
                                'channel_partner_ids': [(4, operator_partner.id) for operator_partner in operator_partners],
                            })
                            operators_added = True
                            result_message = script.response
                            _logger.info("Added operators %s to channel ID %s", operator_partners.mapped('name'), channel.id)
                        else:
                            _logger.warning("No partner IDs found for operators in chatbot configuration ID %s", chatbot_config.id)
                    else:
                        _logger.warning("No operators found in chatbot configuration for config ID %s", config.id)

                else:
                    record = model.sudo().create({'partner_id': partner.id,'name':f'chatbot - {partner.name}'})
                    _logger.info("Created new record ID %s in model %s: %s", record.id, action.binding_id.model, record.name if 'name' in record else 'Unnamed')
                    result_message = script.response
            except Exception as e:
                _logger.error("Failed to create record in model %s for partner ID %s: %s", action.binding_id.model, partner.id, str(e))
                result_message = f"Failed to create record in {action.binding_id.model}: {str(e)}"
        else:
            _logger.warning("No binding_id defined for action ID %s", action.id)
            result_message = script.response
            _logger.info("Action result: %s", result_message)

        return operators_added, result_message