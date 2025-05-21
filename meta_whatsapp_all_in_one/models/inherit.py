from odoo import models, fields, api ,_
from odoo.exceptions import UserError
import base64
import secrets
import lxml.etree as ET
from markupsafe import escape
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import phonenumbers

class ResPartner(models.Model):
    _inherit = "res.partner"

    normalized_phone = fields.Char(string="Normalized Phone", compute="_compute_normalized_phone", store=True)
    normalized_mobile = fields.Char(string="Normalized Mobile", compute="_compute_normalized_mobile", store=True)

    @api.depends("phone")
    def _compute_normalized_phone(self):
        for partner in self:
            partner.normalized_phone = self.normalize_phone_number(partner.phone) if partner.phone else False

    @api.depends("mobile")
    def _compute_normalized_mobile(self):
        for partner in self:
            partner.normalized_mobile = self.normalize_phone_number(partner.mobile) if partner.mobile else False

    def normalize_phone_number(self, number):
        """
        Normalize a phone number to E.164 format.
        """
        try:
            number = ''.join(char for char in str(number) if char.isdigit() or char == '+')
            if str(number).startswith('00'):
                number = str(number)[2:]
            if str(number).startswith('0'):
                number = str(number).lstrip('0')
            if str(number).startswith('+'):
                number = str(number).lstrip('+')
            normalized = ''.join(filter(str.isdigit, number))
            parsed_number = phonenumbers.parse(normalized)
            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
             return number

class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_providers = fields.Many2many(
        'whatsapp.config',
        string="Allowed WhatsApp Providers",
        help="WhatsApp configurations this user is allowed to use for sending messages."
    )
    default_provider = fields.Many2one(
        'whatsapp.config',
        string="Default WhatsApp Provider",
        domain="[('id', 'in', allowed_providers)]",
        help="Default WhatsApp configuration used for sending messages."
    )
class MailMessage(models.Model):
    _inherit = 'mail.message'

    whatsapp_message_id = fields.Char(string="WhatsApp Message ID")

class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    whatsapp_config_id = fields.Many2one('whatsapp.config',string="WhatsApp Message ID")