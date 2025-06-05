{
    'name': 'Meta WhatsApp Helpdesk',
    'version': '18.0.1.0.0',
    'category': 'Helpdesk',
    'summary': 'Send WhatsApp messages for Helpdesk tickets',
    'description': """
        This module allows users to send WhatsApp messages for Helpdesk tickets in Odoo 18 Enterprise,
        including templates, custom messages, and PDF attachments.
    """,
    'author': '',
    'depends': [
        'helpdesk',  # Available only in Odoo Enterprise
        'meta_whatsapp_all_in_one',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/helpdesk_ticket_views.xml',
        'views/whatsapp_helpdesk_wizard_views.xml',
        'views/custom_helpdesk_report.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}