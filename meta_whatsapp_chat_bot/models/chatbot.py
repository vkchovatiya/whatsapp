# -*- coding: utf-8 -*-
import base64
from odoo.exceptions import UserError 
import requests
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class ChatbotConfiguration(models.Model):
    _name = 'chatbot.configuration'
    _description = 'WhatsApp Chatbot  Configuration'

    name = fields.Char( 
        string="Name", 
    )
    config_id = fields.Many2one('whatsapp.config' ,
        string="Account", 
    )
    operator_ids = fields.Many2many(
        'res.users',
        string="Operators",
        help="Users who can operate this WhatsApp configuration"
    )
    action_ids = fields.Many2many(
        comodel_name='whatsapp.action', 
        string="Actions", 
        domain="[('configuration_id', '=', id)]"
    )
    script_ids = fields.One2many(
        comodel_name='chatbot.script',
        inverse_name='configuration_id',
        string="Scripts",
        help="Scripts defining the sequence of steps for the chatbot."
    )
 
class ChatbotScript(models.Model):
    _name = 'chatbot.script'
    _description = 'Chatbot Script'
    _order = 'sequence'
    _rec_name='message'

    sequence = fields.Integer(
        string="Sequence", 
        help="Order in which the script steps are executed."
    )
    step_type = fields.Selection(
        selection=[
            ('message', 'Message'),
            ('template', 'Template'),
            ('interactive', 'Interactive'),
            ('action', 'Action'),
        ],
        string="Script Type",
        required=True,
        help="Type of step to perform in the chatbot flow."
    )
    message = fields.Char('Message')
    response = fields.Char('Response')
    parent_script = fields.Many2one(
        comodel_name='chatbot.script',
        string="Parent Script", 
        help="Parent script for hierarchical script steps."
    )
    template_id = fields.Many2one(
        comodel_name='whatsapp.template',
        string="Template"
    )
    configuration_id = fields.Many2one(
        comodel_name='chatbot.configuration',
        string="Chatbot Configuration",
        required=True,
        ondelete='cascade',
        help="The chatbot configuration this script belongs to."
    )
    action_id = fields.Many2one(
        comodel_name='whatsapp.action',
        string="Action", 
    )
 
class whatsappaction(models.Model):
    _name = 'whatsapp.action'
    _rec_name = 'action_name'

    action_name = fields.Char('Action Name')
    binding_id = fields.Many2one(
        'ir.model',
        string="Binding Model", 
    )
    configuration_id = fields.Many2one(
        comodel_name='chatbot.configuration',
        string="Chatbot Configuration",  
    )
