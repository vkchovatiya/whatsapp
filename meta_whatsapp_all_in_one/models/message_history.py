# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class WhatsAppMessageHistory(models.Model):
    _name = 'whatsapp.message.history'
    _description = 'WhatsApp Message History'

    number = fields.Char(
        string="Number",
        help="Phone number of the recipients"
    )
    user = fields.Many2one('res.users', 'Users')
    message = fields.Text(
        string="Message",
        help="Message content that was sent"
    )
    config_id = fields.Many2one(
        'whatsapp.config',
        string="Configuration",
        required=True,
        help="WhatsApp configuration used to send the message"
    )
    template_id = fields.Many2one(
        'whatsapp.template',
        string="Template",
        help="Template used for the message, if any"
    )
    attachment = fields.Binary(
        string="Attachment",
        help="Attached file sent with the message, if any"
    )
    attachment_filename = fields.Char(
        string="Attachment Filename",
        help="Filename of the attachment"
    )
    send_date = fields.Datetime(
        string="Send Date",
        default=fields.Datetime.now,
        help="Date and time when the message was sent"
    )
    received_date = fields.Datetime(
        string="Received Date",
        default=fields.Datetime.now,
        help="Date and time when the message was received"
    )
    status = fields.Selection(
        [('sent', 'Sent'), ('delivered', 'Delivered'), ('read', 'Read'), ('received', 'Received'), ('failed', 'Failed')],
        string="Status",
        default='sent',
        help="Status of the message delivery"
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Recipient",
        help="Partner associated with the recipient phone number"
    )
    message_id = fields.Char(
        string="Message ID",
        help="WhatsApp message ID (wamid) for tracking status updates"
    )
    conversation_id = fields.Char(
        string="Conversation ID",
        help="WhatsApp Conversation ID for tracking status updates"
    )
    reply_to_message_id = fields.Char(
        string="Reply to Message ID",
        help="WhatsApp message ID of the message this is a reply to"
    )
    is_message_sent = fields.Boolean('send message')