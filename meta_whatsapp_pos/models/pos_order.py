from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import base64
from odoo.http import request

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    def action_send_whatsapp(self):
        """Open the WhatsApp composer wizard for the POS order."""
        self.ensure_one()

        # Check if the order has a customer
        if not self.partner_id:
            raise UserError(_("No customer is set for this order. Please set a customer to send a WhatsApp message."))

        # Check if the customer has a phone number
        if not self.partner_id.mobile and not self.partner_id.phone:
            raise UserError(
                _("The customer does not have a phone number. Please add a phone number to send a WhatsApp message."))

        # Prepare the context for the wizard
        context = {
            'default_order_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_phone': self.partner_id.mobile or self.partner_id.phone,
        }

        # Return the action to open the WhatsAppPosWizard
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp Message'),
            'res_model': 'whatsapp.pos.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }

    def send_whatsapp_message(self, phone, message, template_id=None, attachment_ids=None, attach_pdf=False, report_type="custom"):
        """Send a WhatsApp message for the POS order using message.configuration."""
        self.ensure_one()

        # Validate inputs
        if not phone or not any(c.isdigit() for c in phone):
            raise ValidationError(_("Please provide a valid phone number."))
        if not message:
            raise UserError(_("Please provide a message to send."))

        # Prepare phone number
        phone = phone.replace('+', '').replace(' ', '')
        if not phone.isdigit():
            raise UserError(_("Invalid phone number format."))

        # Update the partner's phone number if needed
        if self.partner_id and self.partner_id.phone != phone:
            self.partner_id.write({'phone': phone})

        # Get the WhatsApp provider configuration
        config_id = self.env['whatsapp.config'].search([], limit=1)
        if not config_id:
            raise UserError(_("No WhatsApp provider is configured. Please configure a provider in the settings."))

        # Handle attachments
        final_attachment_ids = attachment_ids or []
        # Generate PDF attachment if requested
        if attach_pdf:
            try:
                report_xml_id = None
                if report_type == "standard":
                    report_xml_id = 'point_of_sale.action_report_pos_order'  # Standard POS order report
                    if not self.env.ref(report_xml_id, raise_if_not_found=False):
                        raise UserError(_("Standard report for POS orders is not available. Please use the custom report."))
                else:
                    report_xml_id = 'meta_whatsapp_pos.action_report_custom_pos_order'  # Custom POS order report
                    if not self.env.ref(report_xml_id, raise_if_not_found=False):
                        raise UserError("Custom report 'meta_whatsapp_pos.action_report_custom_pos_order' not found. Please ensure the report is configured.")

                _logger.info(f"Attempting to load report with XML ID: {report_xml_id}")
                report = self.env.ref(report_xml_id)
                # Use _render_qweb_pdf with the correct arguments
                pdf_content = self.env['ir.actions.report'].sudo()._render_qweb_pdf(report_xml_id, [self.id])[0]
                if len(pdf_content) > 100 * 1024 * 1024:
                    raise UserError(_('The generated PDF exceeds WhatsApp\'s 100MB file size limit.'))
                attachment = self.env['ir.attachment'].create({
                    'name': f"{self.name}_order.pdf",
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'mimetype': 'application/pdf',
                    'res_model': 'pos.order',
                    'res_id': self.id,
                })
                final_attachment_ids.append(attachment.id)
            except Exception as e:
                _logger.error(f"Failed to generate PDF for POS order {self.id}: {str(e)}")
                raise UserError(_('Failed to generate the POS order PDF: %s') % str(e))

        # Create a temporary MessageConfiguration record to send the message
        message_config = self.env['message.configuration'].new({
            'recipient': self.partner_id.id if self.partner_id else False,
            'config_id': config_id.id,
            'number': phone,
            'template_id': template_id if template_id else False,
            'message': message if message else False,
            'attachment_ids': [(6, 0, final_attachment_ids)] if final_attachment_ids else False,
        })

        # Call the action_send_message method from MessageConfiguration
        try:
            result = message_config.action_send_message()
            # Log the message in whatsapp.message.history
            attachment_record = self.env['ir.attachment'].browse(
                final_attachment_ids[0]) if final_attachment_ids else None

            # Search for existing message history record
            history = self.env['whatsapp.message.history'].search([
                ('partner_id', '=', self.partner_id.id),
                ('message', '=', message)
            ], limit=1)

            if history and attachment_record:
                history.write({
                    'attachment': attachment_record.datas,
                    'attachment_filename': attachment_record.name,
                })

            return {'success': True, 'message': _("WhatsApp message sent successfully.")}
        except Exception as e:
            _logger.error(f"Failed to send WhatsApp message for POS order {self.name}: {str(e)}")
            raise UserError(_("Failed to send WhatsApp message: %s") % str(e))