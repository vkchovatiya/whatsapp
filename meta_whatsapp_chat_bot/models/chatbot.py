# -*- coding: utf-8 -*-
import base64
from odoo.exceptions import UserError
import requests
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class ChatbotConfiguration(models.TransientModel):
    _name = 'chatbot.configuration'
    _description = 'WhatsApp Chatbot  Configuration'

    name = fields.Char(
        string="Name",
    )