{
    'name': 'Meta WhatsApp Purchase',
    'version': '18.0.1.0.0',
    'category': 'Purchases',
    'summary': 'Send WhatsApp messages for purchase orders',
    'description': """
        This module allows users to send WhatsApp messages for purchase orders in Odoo 18,
        including templates, custom messages, and PDF attachments.
    """,
    'author': '',
    'depends': [
        'purchase',
        'meta_whatsapp_all_in_one',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/whatsapp_purchase_wizard_views.xml',
        'views/custom_purchase_report.xml',
        'views/purchase_order_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}