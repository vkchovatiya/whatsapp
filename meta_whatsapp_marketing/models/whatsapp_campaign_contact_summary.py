# -*- coding: utf-8 -*-
# Part of Creyox Technologies.

from odoo import models, fields

class WhatsAppCampaignContactSummary(models.Model):
    _name = 'whatsapp.campaign.contact.summary'
    _description = 'WhatsApp Campaign Contact Message Summary'

    campaign_id = fields.Many2one('whatsapp.marketing.campaign', string="Campaign", required=True)
    partner_id = fields.Many2one('res.partner', string="Contact")
    whatsapp_number = fields.Char(string="WhatsApp Number")
    message_count = fields.Integer(string="Number of Messages")