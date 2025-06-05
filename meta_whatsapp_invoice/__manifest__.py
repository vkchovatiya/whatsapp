# -*- coding: utf-8 -*-

{
    'name': 'Meta WhatsApp Invoice',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Send WhatsApp messages for invoices',
    'description': """
        This module allows users to send WhatsApp messages for invoices in Odoo 18,
        including templates, custom messages, and PDF attachments.
    """,
    'author': '',
    'depends': [
        'account',
        'meta_whatsapp_all_in_one',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
        'views/whatsapp_invoice_wizard_views.xml',
        'views/custom_invoice_report.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}