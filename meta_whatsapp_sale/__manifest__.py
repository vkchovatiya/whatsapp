{
    'name': 'Meta WhatsApp Sale',
    'version': '18.0',
    'category': 'Sales',
    'summary': 'Send sale orders and quotations via WhatsApp with dynamic templates and media attachments',
    'description': """
        This module integrates WhatsApp with Odoo Sales to send quotations and sale orders to customers.
        Features:
        - Send quotations/sale orders via WhatsApp.
        - Use dynamic message templates.
        - Attach media files (doc, PDF, image, video, audio).
        - Log message history.
    """,
    'author': '',
    'depends': ['sale_management', 'meta_whatsapp_marketing', 'mail','meta_whatsapp_all_in_one'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
        'views/whatsapp_sale_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}