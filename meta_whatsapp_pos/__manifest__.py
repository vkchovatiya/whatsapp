{
    'name': 'Meta WhatsApp POS',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Send WhatsApp messages for POS orders',
    'description': """
        This module allows users to send WhatsApp messages for POS orders in Odoo 18,
        including templates, custom messages, and PDF attachments of the order receipt.
    """,
    'author': '',
    'depends': [
        'point_of_sale',
        'meta_whatsapp_all_in_one',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_order_views.xml',
        'views/whatsapp_pos_wizard_views.xml',
        'views/custom_pos_report.xml',
        'views/menu.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'meta_whatsapp_pos/static/src/app/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
