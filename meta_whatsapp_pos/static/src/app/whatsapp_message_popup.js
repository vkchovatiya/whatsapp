import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";

export class WhatsAppMessagePopup extends Component {
    static template = "meta_whatsapp_pos.WhatsAppMessagePopup";
    static components = { Dialog };
    static props = {
        title: String,
        orderId: Number,
        orderName: String,
        phone: String,
        getPayload: Function,
        close: Function,
    };

    setup() {
        this.state = useState({
            phone: this.props.phone || "",
            message: this._getDefaultMessage(),
            template_id: null, // New: WhatsApp template ID
            attachment_ids: [], // New: List of attachment IDs
            attach_pdf: true,  // New: Checkbox for attaching PDF
            report_type: "custom", // New: Report type selection
            templates: [], // New: List of available WhatsApp templates
        });
        this.inputRefs = {
            phone: useRef("phone"),
            message: useRef("message"),
            attachments: useRef("attachments"), // New: Reference to file input
        };
        this.pos = usePos();
        this.notification = useService("notification");
        this.orm = useService("orm");

        // Load WhatsApp templates on mount
        onMounted(async () => {
            await this.loadTemplates();
            // Focus the phone input on mount
            setTimeout(() => {
                if (this.inputRefs.phone.el) {
                    this.inputRefs.phone.el.focus();
                }
            }, 0);
        });
    }

    async loadTemplates() {
        try {
            const templates = await this.orm.call("whatsapp.template", "search_read", [
                [], ["id", "name", "message"]
            ]);
            this.state.templates = templates;
        } catch (error) {
            this.notification.add(_t("Failed to load WhatsApp templates."), { type: "danger" });
        }
    }

    onTemplateChange(event) {
        const templateId = parseInt(event.target.value, 10);
        const selectedTemplate = this.state.templates.find(t => t.id === templateId);
        this.state.template_id = templateId || null;
        if (selectedTemplate) {
            // Pre-fill the message with the template's message
            this.state.message = selectedTemplate.message;
        } else {
            // Reset to default message if no template is selected
            this.state.message = this._getDefaultMessage();
        }
    }

    async onFileChange(event) {
        const files = event.target.files;
        if (!files.length) return;

        try {
            const attachmentPromises = Array.from(files).map(async (file) => {
                // Read file content as base64
                const base64Content = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result.split(',')[1]);
                    reader.onerror = reject;
                    reader.readAsDataURL(file);
                });

                // Create attachment in the backend
                const attachment = await this.orm.call("ir.attachment", "create", [{
                    name: file.name,
                    type: "binary",
                    datas: base64Content,
                    mimetype: file.type,
                    res_model: "pos.order",
                    res_id: this.props.orderId,
                }]);
                return attachment;
            });

            const newAttachmentIds = await Promise.all(attachmentPromises);
            this.state.attachment_ids = [...this.state.attachment_ids, ...newAttachmentIds];
            this.inputRefs.attachments.el.value = ""; // Clear the file input
        } catch (error) {
            this.notification.add(_t("Failed to upload attachments."), { type: "danger" });
        }
    }

    removeAttachment(attachmentId) {
        this.state.attachment_ids = this.state.attachment_ids.filter(id => id !== attachmentId);
        // Optionally, delete the attachment from the backend
        this.orm.call("ir.attachment", "unlink", [[attachmentId]]);
    }

    onAttachPdfChange(event) {
        this.state.attach_pdf = event.target.checked;
    }

    onReportTypeChange(event) {
        this.state.report_type = event.target.value;
    }

    _getDefaultMessage() {
        return _t("Here is your order receipt: %s", this.props.orderName);
    }

    async send() {
        const { phone, message, template_id, attachment_ids, attach_pdf, report_type } = this.state;
        if (!phone) {
            this.notification.add(_t("Please enter a phone number."), { type: "warning" });
            return;
        }
        if (!message) {
            this.notification.add(_t("Please enter a message."), { type: "warning" });
            return;
        }

        try {
            // Call the backend method to send the WhatsApp message
            const result = await this.pos.data.call("pos.order", "send_whatsapp_message", [
                [this.props.orderId], phone, message, template_id, attachment_ids, attach_pdf, report_type
            ]);
            // Show success notification
            this.notification.add(result.message, { type: "success" });
            // Close the dialog
            this.props.close();
        } catch (error) {
            // Handle error and show error notification
            const errorMessage = error.message || _t("Failed to send WhatsApp message. Please try again.");
            this.notification.add(errorMessage, { type: "danger" });
        }
    }

    close() {
        this.props.close();
    }
}