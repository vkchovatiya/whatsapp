{
    'name': 'Meta WhatsApp Inventory',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Send WhatsApp messages for inventory transfers',
    'description': """
        This module allows users to send WhatsApp messages for inventory transfers in Odoo 18,
        including templates, custom messages, and PDF attachments.
    """,
    'author': '',
    'depends': [
        'stock',
        'meta_whatsapp_all_in_one',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
        'views/whatsapp_inventory_wizard_views.xml',
        'views/custom_inventory_report.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}