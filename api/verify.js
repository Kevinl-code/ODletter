export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const { tlName, eventName, code } = req.body;

    // Pull environmental secrets securely on server side execution
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;

    if (!token || !chatId) {
        return res.status(500).json({ error: 'Server environmental credentials configuration missing.' });
    }

    const textAlert = `🚨 *OD Letter Authorization Request*\n\n` +
                      `👤 *Requester/TL:* ${tlName}\n` +
                      `🏆 *Event:* ${eventName}\n` +
                      `🔢 *Security Verification PIN:* \`${code}\` \n\n` +
                      `If you did not request this, do not share this PIN code.`;

    const telegramUrl = `https://api.telegram.org/bot${token}/sendMessage`;

    try {
        const telegramResponse = await fetch(telegramUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chat_id: chatId,
                text: textAlert,
                parse_mode: 'Markdown'
            })
        });

        if (telegramResponse.ok) {
            return res.status(200).json({ success: true });
        } else {
            return res.status(502).json({ error: 'Telegram API delivery failure.' });
        }
    } catch (err) {
        return res.status(500).json({ error: 'Internal server error.' });
    }
}
