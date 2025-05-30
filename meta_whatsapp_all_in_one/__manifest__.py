# -*- coding: utf-8 -*-
# Part of Creyox Technologies
{
    "name": "Odoo Whatsapp Connector",
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
        "base",'contacts',
        # "web",
        # "point_of_sale",
        # 'sale_management'
        # ,'account',
    ],
    "data": [
        'security/ir.model.access.csv',
        'views/configuration.xml',
        'views/message_template.xml',
        'views/message_configure.xml',
        'views/message_history.xml',
        'views/res_partner.xml',
    ],
    # 'assets': {
    #     'web.assets_backend': [
    #             'meta_whatsapp_all_in_one/static/src/css/config.css'
    #         ],
    #     },
    "installable": True,
    "auto_install": False,
    "application": True,
}