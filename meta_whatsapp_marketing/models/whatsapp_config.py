# -*- coding: utf-8 -*-
# Part of Creyox Technologies.

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class WhatsAppMarketingCampaign(models.Model):
    _name = 'whatsapp.marketing.campaign'
    _description = 'WhatsApp Marketing Campaign'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    in_queue_percentage = fields.Char(string='In Queue(%)')
    sent_percentage = fields.Char(string='Sent(%)')
    delivered_percentage = fields.Char(string='Delivered(%)')
    received_percentage = fields.Char(string='Received(%)')
    read_percentage = fields.Char(string='Read(%)')
    fail_percentage = fields.Char(string='Fail(%)')
    recipients_model_id = fields.Many2one("ir.model",
        string="Recipients Model",
    )
    selected_model = fields.Char(string='Selected Model' , store=True)




    @api.onchange('recipients_model_id')
    def _onchange_recipients_model(self):
        if self.recipients_model_id.model == 'whatsapp.messaging.lists':
            self.selected_model = self.recipients_model_id.model
        if self.recipients_model_id.model == 'res.partner':
            self.selected_model = self.recipients_model_id.model

    company_id = fields.Many2one(
        'res.company', string="Company", default=lambda self: self.env.company
    )
    messaging_list_id = fields.Many2one(
        'whatsapp.messaging.lists',
        string="Messaging List",
        help="Select a messaging list to send messages to its contacts"
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_queue', 'In Queue'),
        ('scheduled', 'Sending'),
        ('sent', 'Sent'),
    ], string='Status', default='draft', tracking=True)
    template_id = fields.Many2one(
        'whatsapp.template',
        string="Select Template",
        help="Template used for the message, if any"
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string="Partners",
        help="Select the customer whom you want to send this marketing campaign"
    )
    message_preview = fields.Text(
        string="Message Preview",
        help="Preview of the selected template's message content"
    )
    config_id = fields.Many2one(
        'whatsapp.config',
        string="Provider",
        help="Linked WhatsApp configuration for API access"
    )
    scheduled_date = fields.Datetime(
        string="Scheduled Send Time",
        help="Time when the campaign messages are scheduled to be sent"
    )

    @api.onchange('messaging_list_id')
    def _onchange_recipients(self):
        """Update partner_ids based on messaging_list_id if recipients_model_id is whatsapp.messaging.lists."""
        self.partner_ids = [(5, 0, 0)]  # Clear existing partners
        if self.recipients_model_id.model == 'whatsapp.messaging.lists':
            # Map contacts to partners (create if not exist)
            partners = []
            for contact in self.messaging_list_id.message_list_contacts_ids:
                partner = self.env['res.partner'].search([
                    ('phone', '=', contact.whatsapp_number),
                    ('phone', '!=', False)
                ], limit=1)
                if not partner:
                    partner = self.env['res.partner'].create({
                        'name': contact.name,
                        'phone': contact.whatsapp_number,
                    })
                partners.append(partner.id)
            self.partner_ids = [(6, 0, partners)]

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Update message_preview when template_id changes."""
        self.message_preview = self.template_id.message if self.template_id else False

    def action_send_now(self):
        """Queue campaign for sending in one hour."""
        self.ensure_one()
        if not self.config_id or not self.template_id or not self.partner_ids:
            raise UserError(_('Please set a provider, template, and recipients before sending.'))
        if self.recipients_model_id.model == 'whatsapp.messaging.lists' and not self.messaging_list_id:
            raise UserError(_('Please select a messaging list.'))
        if self.recipients_model_id.model == 'res.partner' and not self.partner_ids:
            raise UserError(_('Please select recipients.'))
        # if self.config_id not in self.env.user.allowed_providers:
        #     raise UserError(_('Selected configuration is not allowed for this user.'))
        self.write({
            'state': 'in_queue',
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Campaign queued for sending.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_schedule(self):
        """Schedule the campaign."""
        self.ensure_one()
        self.write({'state': 'scheduled'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Campaign scheduled successfully!'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cancel(self):
        """Cancel the campaign."""
        _logger.info("Cancel called for campaign %s", self.name)
        self.ensure_one()
        self.write({'state': 'draft', 'scheduled_date': False})
        print(self.selected_model)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Campaign cancelled.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_test(self):
        """Test the campaign by opening a wizard to send a single message."""
        _logger.info("Test called for campaign %s", self.name)
        self.ensure_one()
        model = self.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Test Campaign Message'),
            'res_model': 'message.configuration',
            'view_mode': 'form',
            'view_id': self.env.ref('meta_whatsapp_all_in_one.view_message_configuration_form').id,
            'target': 'new',
            'context': {
                'default_config_id': self.config_id.id,
                'default_template_id': self.template_id.id,
                'default_message': self.message_preview,
                'default_model': model.id,
            }
        }

    def _cron_send_queued_campaigns(self):
        """Send messages for queued campaigns ready to be processed."""
        now = fields.Datetime.now()
        campaigns = self.env['whatsapp.marketing.campaign'].search([
            ('state', '=', 'in_queue')
        ])
        for campaign in campaigns:
            try:
                campaign._send_campaign_messages()
                campaign.write({'state': 'sent', 'scheduled_date': False})
                _logger.info("Campaign %s sent successfully", campaign.name)
            except Exception as e:
                _logger.error("Failed to send campaign %s: %s", campaign.name, str(e))
                campaign.write({'state': 'draft', 'scheduled_date': False})
                campaign.message_post(body=_('Failed to send campaign: %s' % str(e)))

    # def _send_campaign_messages(self):
    #     """Send template-based messages to partner_ids using the Meta WhatsApp API."""
    #     self.ensure_one()
    #     if not self.config_id or not self.template_id or not self.partner_ids:
    #         raise UserError(_('Missing provider, template, or recipients.'))
    #
    #     headers = {
    #         'Authorization': f'Bearer {self.config_id.access_token}',
    #         'Content-Type': 'application/json',
    #     }
    #     url = f"{self.config_id.api_url}/{self.config_id.instance_id}/messages"
    #     message_history = self.env['whatsapp.message.history']
    #
    #     for partner in self.partner_ids:
    #         number = partner.phone
    #         if not number:
    #             _logger.warning("Partner %s has no phone number", partner.name)
    #             # message_history.create({
    #             #     'campaign_id': self.id,
    #             #     'partner_id': partner.id,
    #             #     'number': number,
    #             #     'user': self.env.user.id,
    #             #     'message': self.message_preview,
    #             #     'config_id': self.config_id.id,
    #             #     'template_id': self.template_id.id,
    #             #     'status': 'failed',
    #             #     'error': _('No phone number provided.'),
    #             # })
    #             continue
    #
    #         if number.startswith('+'):
    #             number = number[1:]
    #
    #         # # Create or get chat channel
    #         # channel = self._get_or_create_chat_channel(partner, self.config_id.id)
    #
    #         # Send template message
    #         payload = {
    #             "messaging_product": "whatsapp",
    #             "to": number,
    #             "type": "template",
    #             "template": {
    #                 "name": self.template_id.name,
    #                 "language": {
    #                     "code": self.template_id.lang.code.replace('-', '_')
    #                 },
    #                 "components": [
    #
    #                 ]
    #             }
    #         }
    #
    #         try:
    #             response = requests.post(url, headers=headers, json=payload)
    #             _logger.info('WhatsApp API response for %s: %s', number, response.text)
    #             response.raise_for_status()
    #             response_data = response.json()
    #             message_id = response_data.get('messages', [{}])[0].get('id')
    #             conversation_id = response_data.get('conversations', [{}])[0].get('id', False)
    #
    #             # # Log message in history
    #             # log_vals = {
    #             #     'campaign_id': self.id,
    #             #     'partner_id': partner.id,
    #             #     'number': number,
    #             #     'user': self.env.user.id,
    #             #     'message': self.message_preview,
    #             #     'config_id': self.config_id.id,
    #             #     'template_id': self.template_id.id,
    #             #     'status': 'sent',
    #             #     'message_id': message_id,
    #             #     'conversation_id': conversation_id,
    #             # }
    #             # history_record = message_history.create(log_vals)
    #             #
    #             # # Create mail.message in channel
    #             # if channel:
    #             #     self.env['mail.message'].sudo().create({
    #             #         'model': 'discuss.channel',
    #             #         'res_id': channel.id,
    #             #         'message_type': 'comment',
    #             #         'subtype_id': self.env.ref('mail.mt_comment').id,
    #             #         'body': self.message_preview,
    #             #         'author_id': self.env.user.partner_id.id,
    #             #         'date': fields.Datetime.now(),
    #             #         'whatsapp_message_id': message_id,
    #             #     })
    #             #     self.env['bus.bus']._sendone(
    #             #         channel, 'discuss.channel/transient_message', {
    #             #             'body': self.message_preview,
    #             #             'author_id': self.env.user.partner_id.id,
    #             #             'channel_id': channel.id,
    #             #         }
    #             #     )
    #
    #         except requests.RequestException as e:
    #             _logger.error("Failed to send message to %s: %s", number, str(e))
    #             message_history.create({
    #                 'campaign_id': self.id,
    #                 'partner_id': partner.id,
    #                 'number': number,
    #                 'user': self.env.user.id,
    #                 'message': self.message_preview,
    #                 'config_id': self.config_id.id,
    #                 'template_id': self.template_id.id,
    #                 'status': 'failed',
    #                 'error': str(e),
    #             })

    def _send_campaign_messages(self):
        """Send template-based messages to recipients using the Meta WhatsApp API."""
        self.ensure_one()
        if not self.config_id or not self.template_id:
            raise UserError(_('Missing provider or template.'))

        headers = {
            'Authorization': f'Bearer {self.config_id.access_token}',
            'Content-Type': 'application/json',
        }
        url = f"{self.config_id.api_url}/{self.config_id.instance_id}/messages"
        message_history = self.env['whatsapp.message.history']

        # Determine recipients based on recipients_model_id
        if self.recipients_model_id.model == 'whatsapp.messaging.lists' and self.messaging_list_id:
            if self.messaging_list_id.recipients_model_id.model == 'whatsapp.messaging.lists.contacts':
                recipients = self.messaging_list_id.message_list_contacts_ids
                recipient_type = 'contact'
            else:
                recipients = self.messaging_list_id.partner_ids
                recipient_type = 'partner'
        else:
            recipients = self.partner_ids
            recipient_type = 'partner'

        if not recipients:
            raise UserError(_('No recipients selected.'))

        for recipient in recipients:
            if recipient_type == 'contact':
                number = recipient.whatsapp_number
                partner_id = self.env['res.partner'].search([('phone', '=', number)], limit=1).id or False
                recipient_name = recipient.name
            else:
                number = recipient.phone or recipient.mobile
                partner_id = recipient.id
                recipient_name = recipient.name

            if not number:
                _logger.warning("Recipient %s has no phone number", recipient_name)
                # message_history.create({
                #     'campaign_id': self.id,
                #     'partner_id': partner_id,
                #     'number': number,
                #     'user': self.env.user.id,
                #     'message': self.message_preview,
                #     'config_id': self.config_id.id,
                #     'template_id': self.template_id.id,
                #     'status': 'failed',
                #     'error': _('No phone number provided.'),
                # })
                continue

            if number.startswith('+'):
                number = number[1:]

            # Send template message
            payload = {
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
                response = requests.post(url, headers=headers, json=payload)
                _logger.info('WhatsApp API response for %s: %s', number, response.text)
                response.raise_for_status()
                response_data = response.json()
                message_id = response_data.get('messages', [{}])[0].get('id')
                conversation_id = response_data.get('conversations', [{}])[0].get('id', False)

                # # Log message in history
                # log_vals = {
                #     'campaign_id': self.id,
                #     'partner_id': partner_id,
                #     'number': number,
                #     'user': self.env.user.id,
                #     'message': self.message_preview,
                #     'config_id': self.config_id.id,
                #     'template_id': self.template_id.id,
                #     'status': 'sent',
                #     'message_id': message_id,
                #     'conversation_id': conversation_id,
                # }
                # history_record = message_history.create(log_vals)

            except requests.RequestException as e:
                _logger.error("Failed to send message to %s: %s", number, str(e))
                message_history.create({
                    'campaign_id': self.id,
                    'partner_id': partner_id,
                    'number': number,
                    'user': self.env.user.id,
                    'message': self.message_preview,
                    'config_id': self.config_id.id,
                    'template_id': self.template_id.id,
                    'status': 'failed',
                    'error': str(e),
                })