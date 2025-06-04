import { _t } from "@web/core/l10n/translation";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { WhatsAppMessagePopup } from "@meta_whatsapp_pos/app/whatsapp_message_popup";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },
    async onSendWhatsApp() {
        const order = this.currentOrder;
        try {
            if (typeof order.id !== "number") {
                this.dialog.add(ConfirmationDialog, {
                    title: _t("Unsynced order"),
                    body: _t("This order is not yet synced to server. Make sure it is synced then try again."),
                });
                return;
            }
            // Check for customer and phone number on the frontend
            if (!order.get_partner()) {
                this.dialog.add(ConfirmationDialog, {
                    title: _t("Error"),
                    body: _t("No customer is set for this order. Please set a customer to send a WhatsApp message."),
                });
                return;
            }
            const partner = order.get_partner();
            const phone = partner.mobile || partner.phone;
            if (!phone) {
                this.dialog.add(ConfirmationDialog, {
                    title: _t("Error"),
                    body: _t("The customer does not have a phone number. Please add a phone number to send a WhatsApp message."),
                });
                return;
            }
            // Open the WhatsAppMessagePopup dialog
            await new Promise((resolve) => {
                this.dialog.add(WhatsAppMessagePopup, {
                    title: _t("Send WhatsApp Message"),
                    orderId: order.id, // Pass the order ID
                    orderName: order.name,
                    phone: phone,
                    getPayload: resolve,
                });
            });
        } catch (error) {
            const errorMessage = error.data?.message || error.message || _t("Failed to send WhatsApp message. Please try again.");
            this.dialog.add(ConfirmationDialog, {
                title: _t("Error"),
                body: errorMessage,
            });
        }
    },
});