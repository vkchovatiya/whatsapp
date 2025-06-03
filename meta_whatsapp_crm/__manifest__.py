# -*- coding: utf-8 -*-

{
    'name': 'Meta WhatsApp CRM',
    'version': '18.0.1.0.0',
    'category': 'CRM',
    'summary': 'Send WhatsApp messages for CRM leads and opportunities',
    'description': """
        This module allows users to send WhatsApp messages for CRM leads and opportunities in Odoo 18,
        including templates, custom messages, and PDF attachments.
    """,
    'author': '',
    'depends': [
        'crm',
        'meta_whatsapp_all_in_one',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_lead_views.xml',
        'views/whatsapp_crm_wizard_views.xml',
        'views/custom_crm_report.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}