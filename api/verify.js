export const config = {
    runtime: 'edge', 
};

export default async function handler(req) {
    if (req.method !== 'POST') {
        return new Response(JSON.stringify({ error: 'Method not allowed' }), {
            status: 405,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    try {
        // Safe Request Extraction Fallback Layer
        let tlName = "Not Provided";
        let eventName = "Not Provided";
        let code = "000000";

        try {
            const body = await req.json();
            if (body) {
                tlName = body.tlName || tlName;
                eventName = body.eventName || eventName;
                code = body.code || code;
            }
        } catch (parseError) {
            console.warn("Incoming stream parse warning, falling back to defaults.");
        }

        const token = process.env.TELEGRAM_BOT_TOKEN;
        const chatId = process.env.TELEGRAM_CHAT_ID;

        if (!token || !chatId) {
            return new Response(JSON.stringify({ error: 'Environment variables are missing on Vercel.' }), {
                status: 500,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        const textAlert = `🚨 *OD Letter Authorization Request*\n\n` +
                          `👤 *Requester/TL:* ${tlName}\n` +
                          `🏆 *Event:* ${eventName}\n` +
                          `🔢 *Security Verification PIN:* \`${code}\` \n\n` +
                          `If you did not request this, do not share this PIN code.`;

        const telegramUrl = `https://api.telegram.org/bot${token}/sendMessage`;

        const telegramResponse = await fetch(telegramUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chat_id: chatId,
                text: textAlert,
                parse_mode: 'Markdown'
            })
        });

        const telegramData = await telegramResponse.json();

        if (telegramResponse.ok && telegramData.ok) {
            return new Response(JSON.stringify({ success: true }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' }
            });
        } else {
            return new Response(JSON.stringify({ error: 'Telegram API rejected request.', details: telegramData }), {
                status: 400,
                headers: { 'Content-Type': 'application/json' }
            });
        }

    } catch (err) {
        return new Response(JSON.stringify({ error: 'System execution failure.', details: err.message }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}
