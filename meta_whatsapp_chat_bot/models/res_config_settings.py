# -*- coding: utf-8 -*-
# Part of Creyox Technologies
from odoo import models, fields, api, _ 
 
class ChatbotConfig(models.TransientModel):
    _inherit = "res.config.settings"
    
    cr_chatbot_id = fields.Many2one(
            "chatbot.configuration", related="company_id.cr_chatbot_id", readonly=False
        )

class ConfigChatbot(models.Model):
    _inherit = "res.company"

    cr_chatbot_id = fields.Many2one(
        "chatbot.configuration",
    )