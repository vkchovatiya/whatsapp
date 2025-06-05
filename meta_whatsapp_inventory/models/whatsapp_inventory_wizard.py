# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError, MissingError

import requests
import logging
import base64

from odoo.http import request

_logger = logging.getLogger(__name__)

class WhatsAppInventoryWizard(models.TransientModel):
    _name = 'whatsapp.inventory.wizard'
    _description = 'Wizard to Send WhatsApp Messages for Inventory Transfers'

    picking_id = fields.Many2one(
        'stock.picking',
        string="Transfer",
        required=True,
        default=lambda self: self.env.context.get('default_picking_id')
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Contact",
        required=True,
        default=lambda self: self.env.context.get('default_partner_id')
    )
    phone = fields.Char(
        string="Phone Number",
        required=True,
        default=lambda self: self.env.context.get('default_phone')
    )
    template_id = fields.Many2one(
        'whatsapp.template',
        string="Template",
        help="Select a WhatsApp message template"
    )
    message = fields.Text(
        string="Message",
        compute='_compute_message',
        store=True,
        readonly=False,
        help="Message content, populated from template or custom"
    )
    config_id = fields.Many2one(
        'whatsapp.config',
        string="WhatsApp Provider",
        required=True,
        default=lambda self: self.env['whatsapp.config'].search([], limit=1)
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string="Attachments",
        help="Attach media files (doc, PDF, image, video, audio)"
    )

    attach_pdf = fields.Boolean(
        string="Attach PDF",
        default=True,
        help="Automatically attach the transfer PDF."
    )

    report_type = fields.Selection(
        [
            ('standard', 'Transfer'),
            ('custom', 'Custom Report'),
        ],
        string="Report Type",
        default='standard',
        help="Select the type of report to attach as a PDF."
    )

    @api.model
    def default_get(self, fields_list):
        """Override default_get to optionally attach a PDF or include transfer data in the message."""
        res = super(WhatsAppInventoryWizard, self).default_get(fields_list)
        picking_id = res.get('picking_id')
        attach_pdf = res.get('attach_pdf', False)
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            # Prepare transfer summary for the message
            transfer_summary = (
                f"Transfer: {picking.name}\n"
                f"Contact: {picking.partner_id.name}\n"
                f"Scheduled Date: {picking.scheduled_date}\n"
                f"Source Location: {picking.location_id.name}\n"
                f"Destination Location: {picking.location_dest_id.name}\n"
                f"State: {picking.state.capitalize()}"
            )
            if not res.get('message'):
                res['message'] = transfer_summary
            if attach_pdf:
                try:
                    report_type = res.get('report_type', 'standard')
                    if report_type == 'standard':
                        report_xml_id = 'stock.action_report_picking'
                    else:
                        report_xml_id = 'meta_whatsapp_inventory.action_report_custom_inventory_transfer'
                    _logger.info("Attempting to load report with XML ID: %s", report_xml_id)
                    report = self.env.ref(report_xml_id)
                    _logger.info("Report loaded successfully: %s (ID: %s)", report.name, report.id)
                    pdf_content = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
                        report_xml_id, [picking.id]
                    )[0]
                    if len(pdf_content) > 100 * 1024 * 1024:
                        raise UserError(_('The generated PDF exceeds WhatsApp\'s 100MB file size limit.'))
                    attachment = self.env['ir.attachment'].create({
                        'name': f"{picking.name}_transfer.pdf",
                        'type': 'binary',
                        'datas': base64.b64encode(pdf_content),
                        'mimetype': 'application/pdf',
                        'res_model': 'stock.picking',
                        'res_id': picking.id,
                    })
                    res['attachment_ids'] = [(4, attachment.id)]
                except MissingError as e:
                    _logger.error("Report with XML ID %s not found: %s", report_xml_id, str(e))
                    raise UserError(
                        _('The report (%s) is missing. Please ensure the report is available in the system. Contact your administrator to verify the module installation.') % report_xml_id
                    )
                except Exception as e:
                    _logger.error("Failed to generate PDF for transfer %s: %s", picking.id, str(e))
                    raise UserError(_('Failed to generate the transfer PDF: %s') % str(e))
        return res

    @api.depends('template_id', 'picking_id')
    def _compute_message(self):
        """Compute the message field by reusing the logic from MessageConfiguration."""
        for wizard in self:
            if not wizard.template_id or not wizard.picking_id:
                wizard.message = False
                continue

            # Get the ir.model record for stock.picking
            picking_model = self.env['ir.model'].search([('model', '=', 'stock.picking')], limit=1)
            if not picking_model:
                raise UserError(_('Model "stock.picking" not found in the system.'))

            # Create a temporary MessageConfiguration record to reuse its method
            message_config = self.env['message.configuration'].new({
                'template_id': wizard.template_id.id,
                'model': picking_model.id,
                'number_field': wizard.picking_id.id,
            })

            try:
                # Call the get_calculated_message_and_parameters method
                calculated_message, _ = message_config.get_calculated_message_and_parameters()
                wizard.message = calculated_message
            except Exception as e:
                _logger.error("Error calculating message for template %s in WhatsAppInventoryWizard: %s",
                              wizard.template_id.name, str(e))
                wizard.message = wizard.template_id.message  # Fallback to raw message if calculation fails

    @api.constrains('phone')
    def _check_phone(self):
        """Validate phone number format."""
        for wizard in self:
            if not wizard.phone or not any(c.isdigit() for c in wizard.phone):
                raise ValidationError(_('Please provide a valid phone number.'))

    def action_send_message(self):
        """Send WhatsApp message by reusing the logic from MessageConfiguration."""
        self.ensure_one()

        # Validate required fields
        if not self.config_id or not (self.template_id or self.message):
            raise UserError(_('Please select a WhatsApp provider and a template or enter a message.'))

        # Prepare phone number
        phone = self.phone.replace('+', '').replace(' ', '')
        if not phone.isdigit():
            raise UserError(_('Invalid phone number format.'))

        # Update the partner’s phone number if needed
        if self.partner_id.phone != self.phone:
            self.partner_id.write({'phone': self.phone})

        # Create a temporary MessageConfiguration record to reuse its method
        message_config = self.env['message.configuration'].new({
            'recipient': self.partner_id.id,
            'config_id': self.config_id.id,
            'number': 'phone',  # Use the 'phone' field of res.partner
            'template_id': self.template_id.id if self.template_id else False,
            'message': self.message if self.message else False,
            'attachment_ids': [(6, 0, self.attachment_ids.ids)] if self.attachment_ids else False,
        })

        # Call the action_send_message method from MessageConfiguration
        try:
            result = message_config.action_send_message()
            return result
        except Exception as e:
            _logger.error("Failed to send WhatsApp message to %s: %s", self.partner_id.name, str(e))
            raise UserError(_('Failed to send message: %s') % str(e))