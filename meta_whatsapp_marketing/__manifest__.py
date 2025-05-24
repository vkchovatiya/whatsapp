# -*- coding: utf-8 -*-
# Part of Creyox Technologies.
{
    'name': 'WhatsApp Marketing',
    'version': '18.0',
    'category': 'Marketing',
    'summary': 'Manage WhatsApp marketing campaigns in Odoo 18',
    'description': """
        A module to create and manage WhatsApp marketing campaigns,
        including contact segmentation, template-based messaging,
        and analytics, integrated with the Meta WhatsApp Business API.
    """,
    'depends': ['meta_whatsapp_all_in_one','mail','contacts'],
    'data': [
        'security/ir.model.access.csv',
        'views/whatsapp_menus.xml',
        'data/cron.xml',
        'views/whatsapp_config_view.xml',
        'views/whatsapp_messaging_lists_contacts.xml',
        'views/whatsapp_messaging_lists_views.xml',
    ],
    'installable': True,
    'application': True,
}