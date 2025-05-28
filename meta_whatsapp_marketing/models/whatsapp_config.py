# -*- coding: utf-8 -*-
# Part of Creyox Technologies.

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging
from datetime import datetime, timedelta
from ast import literal_eval

_logger = logging.getLogger(__name__)

class WhatsAppMarketingCampaign(models.Model):
    _name = 'whatsapp.marketing.campaign'
    _description = 'WhatsApp Marketing Campaign'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    in_queue_percentage = fields.Float(string='In Queue(%)', compute='_compute_statistics')
    sent_percentage = fields.Float(string='Sent(%)', compute='_compute_statistics')
    delivered_percentage = fields.Float(string='Delivered(%)', compute='_compute_statistics')
    received_percentage = fields.Float(string='Received(%)', compute='_compute_statistics')
    read_percentage = fields.Float(string='Read(%)', compute='_compute_statistics')
    fail_percentage = fields.Float(string='Fail(%)', compute='_compute_statistics')
    recipients_model_id = fields.Many2one(
        'ir.model',
        string="Recipients Model",
        domain="[('model', 'in', ('res.partner', 'whatsapp.messaging.lists'))]",
    )
    selected_model = fields.Char(string='Selected Model', store=True)
    message_history_ids = fields.One2many(
        'whatsapp.message.history',
        'campaign_id',
        string="Message History",
        help="History of messages sent in this campaign"
    )
    contact_message_summary = fields.One2many(
        'whatsapp.campaign.contact.summary',
        'campaign_id',
        string="Contact Message Summary",
        compute='_compute_contact_message_summary',
        help="Summary of messages sent per contact"
    )
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
    mailing_domain = fields.Char(
        string='Filter Domain',
        default='[]',
        help="Domain to filter recipients for the campaign"
    )
    use_mailing_domain = fields.Boolean(
        string='Use Filter Domain',
        default=False,
        help="Enable to apply a domain filter for selecting recipients"
    )
    # mailing_model_real = fields.Char(
    #     string='Real Recipients Model',
    #     compute='_compute_mailing_model_real',
    #     help="Technical field to determine the model for the domain widget"
    # )
    #
    # @api.depends('recipients_model_id')
    # def _compute_mailing_model_real(self):
    #     """Compute the real model name for the domain widget."""
    #     for campaign in self:
    #         campaign.mailing_model_real = campaign.recipients_model_id.model if campaign.recipients_model_id else False
    #
    # @api.constrains('mailing_domain', 'recipients_model_id')
    # def _check_mailing_domain(self):
    #     """Validate the mailing domain."""
    #     for campaign in self:
    #         if campaign.mailing_domain and campaign.mailing_domain != '[]' and campaign.recipients_model_id:
    #             try:
    #                 self.env[campaign.recipients_model_id.model].search_count(literal_eval(campaign.mailing_domain))
    #             except Exception:
    #                 raise ValidationError(_("The filter domain is not valid for the selected recipients model."))

    @api.depends('message_history_ids')
    def _compute_statistics(self):
        """Compute percentages based on message history statuses."""
        default_vals = {
            'in_queue_percentage': 0.0,
            'sent_percentage': 0.0,
            'delivered_percentage': 0.0,
            'received_percentage': 0.0,
            'read_percentage': 0.0,
            'fail_percentage': 0.0,
        }
        if not self.ids:
            self.update(default_vals)
            return

        self.env.cr.execute("""
            SELECT
                c.id as campaign_id,
                COUNT(h.id) AS total,
                COUNT(h.id) FILTER (WHERE h.status = 'in_queue') AS in_queue,
                COUNT(h.id) FILTER (WHERE h.status = 'sent') AS sent,
                COUNT(h.id) FILTER (WHERE h.status = 'delivered') AS delivered,
                COUNT(h.id) FILTER (WHERE h.status = 'received') AS received,
                COUNT(h.id) FILTER (WHERE h.status = 'read') AS read,
                COUNT(h.id) FILTER (WHERE h.status = 'failed') AS failed
            FROM
                whatsapp_message_history h
            RIGHT JOIN
                whatsapp_marketing_campaign c
                ON (c.id = h.campaign_id)
            WHERE
                c.id IN %s
            GROUP BY
                c.id
        """, (tuple(self.ids),))

        all_stats = self.env.cr.dictfetchall()
        stats_per_campaign = {stats['campaign_id']: stats for stats in all_stats}

        for campaign in self:
            stats = stats_per_campaign.get(campaign.id)
            if not stats:
                campaign.update(default_vals)
            else:
                total = stats['total'] or 1
                campaign.update({
                    'in_queue_percentage': round(100.0 * stats['in_queue'] / total, 2),
                    'sent_percentage': round(100.0 * stats['sent'] / total, 2),
                    'delivered_percentage': round(100.0 * stats['delivered'] / total, 2),
                    'received_percentage': round(100.0 * stats['received'] / total, 2),
                    'read_percentage': round(100.0 * stats['read'] / total, 2),
                    'fail_percentage': round(100.0 * stats['failed'] / total, 2),
                })

    @api.depends('message_history_ids')
    def _compute_contact_message_summary(self):
        """Compute contact-based message summary."""
        for campaign in self:
            summary_data = {}
            for message in campaign.message_history_ids:
                if not message.partner_id and not message.number:
                    _logger.warning("Skipping message ID %s in campaign %s: no partner_id or number", message.id, campaign.name)
                    continue
                key = message.partner_id.id if message.partner_id else message.number
                if key not in summary_data:
                    summary_data[key] = {
                        'partner_id': message.partner_id.id,
                        'whatsapp_number': message.number,
                        'message_count': 0,
                    }
                summary_data[key]['message_count'] += 1

            summary_records = [
                (0, 0, {
                    'campaign_id': campaign.id,
                    'partner_id': data['partner_id'] or False,
                    'whatsapp_number': data['whatsapp_number'] or '',
                    'message_count': data['message_count'],
                }) for data in summary_data.values()
            ]
            campaign.contact_message_summary = summary_records or [(5, 0, 0)]

    @api.onchange('recipients_model_id')
    def _onchange_recipients_model(self):
        if self.recipients_model_id.model in ('whatsapp.messaging.lists', 'res.partner'):
            self.selected_model = self.recipients_model_id.model
            self.mailing_domain = '[]'  # Reset domain when model changes

    @api.onchange('messaging_list_id')
    def _onchange_recipients(self):
        """Update partner_ids based on messaging_list_id if recipients_model_id is whatsapp.messaging.lists."""
        self.partner_ids = [(5, 0, 0)]
        if self.recipients_model_id.model == 'whatsapp.messaging.lists' and self.messaging_list_id:
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
        """Queue campaign for sending and log in_queue status."""
        self.ensure_one()
        if not self.config_id or not self.template_id:
            raise UserError(_('Please set a provider, template, and recipients before sending.'))
        if self.recipients_model_id.model == 'whatsapp.messaging.lists' and not self.messaging_list_id:
            raise UserError(_('Please select a messaging list.'))
        if self.recipients_model_id.model == 'res.partner' and not self.partner_ids and (not self.use_mailing_domain or self.mailing_domain == '[]'):
            raise UserError(_('Please select recipients or enable and define a filter domain.'))

        # Determine recipients
        if self.recipients_model_id.model == 'whatsapp.messaging.lists' and self.messaging_list_id:
            if self.messaging_list_id.msg_lists_recipients_model_id.model == 'whatsapp.messaging.lists.contacts':
                recipients = self.messaging_list_id.message_list_contacts_ids
                recipient_type = 'contact'
            else:
                recipients = self.messaging_list_id.partner_ids
                recipient_type = 'partner'
        else:
            if not self.partner_ids and self.use_mailing_domain and self.mailing_domain != '[]':
                try:
                    domain = literal_eval(self.mailing_domain)
                    recipients = self.env['res.partner'].search(domain)
                except Exception:
                    raise UserError(_('Invalid filter domain.'))
            else:
                recipients = self.partner_ids
            recipient_type = 'partner'

        # Log in_queue status for each recipient
        message_history = self.env['whatsapp.message.history']
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
                _logger.warning("Skipping recipient %s: no phone number", recipient_name)
                continue

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
            if self.messaging_list_id.msg_lists_recipients_model_id.model == 'whatsapp.messaging.lists.contacts':
                recipients = self.messaging_list_id.message_list_contacts_ids
                recipient_type = 'contact'
            else:
                recipients = self.messaging_list_id.partner_ids
                recipient_type = 'partner'
        else:
            if not self.partner_ids and self.use_mailing_domain and self.mailing_domain != '[]':
                try:
                    domain = literal_eval(self.mailing_domain)
                    recipients = self.env['res.partner'].search(domain)
                except Exception:
                    raise UserError(_('Invalid filter domain.'))
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
                message_history.create({
                    'campaign_id': self.id,
                    'partner_id': partner_id,
                    'number': number,
                    'user': self.env.user.id,
                    'date': fields.Datetime.now(),
                    'message': self.message_preview,
                    'config_id': self.config_id.id,
                    'template_id': self.template_id.id,
                    'status': 'failed',
                    'error': _('No phone number provided.'),
                })
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

                # Log message in history
                log_vals = {
                    'campaign_id': self.id,
                    'partner_id': partner_id,
                    'number': number,
                    'user': self.env.user.id,
                    'date': fields.Datetime.now(),
                    'message': self.message_preview,
                    'config_id': self.config_id.id,
                    'template_id': self.template_id.id,
                    'status': 'sent',
                    'message_id': message_id,
                    'conversation_id': conversation_id,
                }
                history_record = message_history.create(log_vals)

            except requests.RequestException as e:
                _logger.error("Failed to send message to %s: %s", number, str(e))
                message_history.create({
                    'campaign_id': self.id,
                    'partner_id': partner_id,
                    'number': number,
                    'user': self.env.user.id,
                    'date': fields.Datetime.now(),
                    'message': self.message_preview,
                    'config_id': self.config_id.id,
                    'template_id': self.template_id.id,
                    'status': 'failed',
                    'error': str(e),
                })