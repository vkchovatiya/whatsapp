# -*- coding: utf-8 -*-
# Part of Creyox Technologies
{
    "name": "Odoo Whatsapp Chatbot",
    "author": "Creyox Technologies",
    "website": "https://www.creyox.com",
    "support": "support@creyox.com",
    "category": "Extra Tools",
    "summary": " ",
    "license": "LGPL-3",
    "version": "18.0",
    "description": """ 
        """,
    "depends": [
        "base", 'meta_whatsapp_all_in_one','mail' 
    ],
    "data": [
        'security/ir.model.access.csv',
        'views/chatbot_configuration.xml',
        'views/history.xml',
        'views/res_config_settings.xml',
    ], 
    "installable": True,
    "auto_install": False,
    "application": True,
}