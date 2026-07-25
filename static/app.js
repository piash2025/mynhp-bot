/* eslint-disable no-undef */
const tg = window.Telegram?.WebApp;
if (tg) tg.expand();

let currentUser = null;

// Get user data from Telegram
if (tg?.initDataUnsafe?.user) {
    currentUser = tg.initDataUnsafe.user;
    fetch("/api/user/track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            user_id: currentUser.id,
            username: currentUser.username,
            first_name: currentUser.first_name,
        }),
    });
}

// ---- Modal ----
function openTool(toolId) {
    const modal = document.getElementById("tool-modal");
    const title = document.getElementById("modal-title");
    const body = document.getElementById("modal-body");
    const result = document.getElementById("modal-result");

    result.classList.add("hidden");
    result.textContent = "";

    const tools = {
        "text-reverse": {
            title: "Text Reverse",
            html: `
                <textarea id="tr-input" placeholder="Type your text here..."></textarea>
                <button class="primary" onclick="doTextReverse()">Reverse</button>
            `,
        },
        "word-count": {
            title: "Word Counter",
            html: `
                <textarea id="wc-input" placeholder="Paste or type your text..."></textarea>
                <button class="primary" onclick="doWordCount()">Count</button>
            `,
        },
        base64: {
            title: "Base64 Encode / Decode",
            html: `
                <textarea id="b64-input" placeholder="Enter text to encode or decode..."></textarea>
                <button class="primary" onclick="doBase64('encode')">Encode</button>
                <button class="secondary" onclick="doBase64('decode')">Decode</button>
            `,
        },
        password: {
            title: "Password Generator",
            html: `
                <label>Length: <input type="number" id="pw-length" value="16" min="4" max="64"></label>
                <label><input type="checkbox" id="pw-upper" checked> Uppercase (A-Z)</label>
                <label><input type="checkbox" id="pw-lower" checked> Lowercase (a-z)</label>
                <label><input type="checkbox" id="pw-numbers" checked> Numbers (0-9)</label>
                <label><input type="checkbox" id="pw-symbols" checked> Symbols (!@#$...)</label>
                <button class="primary" onclick="doPassword()">Generate Password</button>
            `,
        },
        "qr-code": {
            title: "QR Code Generator",
            html: `
                <input type="text" id="qr-input" placeholder="Enter URL or text...">
                <button class="primary" onclick="doQRCode()">Generate QR Code</button>
            `,
        },
        "json-formatter": {
            title: "JSON Formatter",
            html: `
                <textarea id="json-input" placeholder='Paste JSON here...\n{"key": "value"}'></textarea>
                <button class="primary" onclick="doJsonFormat()">Format JSON</button>
            `,
        },
        "color-picker": {
            title: "Color Picker",
            html: `
                <input type="color" id="cp-input" value="#3390ec">
                <div class="color-preview" id="cp-preview" style="background:#3390ec;"></div>
                <div class="color-hex" id="cp-hex">#3390ec</div>
                <button class="primary" onclick="doColorCopy()">Copy HEX Value</button>
            `,
        },
        lorem: {
            title: "Lorem Ipsum Generator",
            html: `
                <label>Number of paragraphs: <input type="number" id="lorem-count" value="3" min="1" max="20"></label>
                <button class="primary" onclick="doLorem()">Generate</button>
            `,
        },
    };

    const tool = tools[toolId];
    if (!tool) return;

    title.textContent = tool.title;
    body.innerHTML = tool.html;
    modal.classList.remove("hidden");

    // Color picker live preview
    if (toolId === "color-picker") {
        const cpInput = document.getElementById("cp-input");
        cpInput.addEventListener("input", function (e) {
            document.getElementById("cp-preview").style.background = e.target.value;
            document.getElementById("cp-hex").textContent = e.target.value;
        });
    }

    trackToolUse();
}

function closeModal() {
    document.getElementById("tool-modal").classList.add("hidden");
}

function showResult(text) {
    const result = document.getElementById("modal-result");
    result.textContent = text;
    result.classList.remove("hidden");
}

function showResultHTML(html) {
    const result = document.getElementById("modal-result");
    result.innerHTML = html;
    result.classList.remove("hidden");
}

// ---- Track ----
async function trackToolUse() {
    if (currentUser) {
        fetch("/api/tool/use", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: currentUser.id }),
        });
    }
}

// ---- Tool Functions ----

function doTextReverse() {
    const input = document.getElementById("tr-input").value;
    showResult(input.split("").reverse().join(""));
}

function doWordCount() {
    const input = document.getElementById("wc-input").value;
    const words = input.trim() ? input.trim().split(/\s+/).length : 0;
    const chars = input.length;
    const charsNoSpace = input.replace(/\s/g, "").length;
    const lines = input.split("\n").length;
    const sentences = input.split(/[.!?]+/).filter((s) => s.trim()).length;
    showResult(
        `Words:            ${words}\n` +
        `Characters:       ${chars}\n` +
        `Without spaces:   ${charsNoSpace}\n` +
        `Lines:            ${lines}\n` +
        `Sentences:        ${sentences}`
    );
}

function doBase64(mode) {
    const input = document.getElementById("b64-input").value;
    try {
        if (mode === "encode") {
            showResult(btoa(unescape(encodeURIComponent(input))));
        } else {
            showResult(decodeURIComponent(escape(atob(input))));
        }
    } catch (e) {
        showResult("Error: Invalid input for " + mode + "\n" + e.message);
    }
}

function doPassword() {
    const length = parseInt(document.getElementById("pw-length").value) || 16;
    const useUpper = document.getElementById("pw-upper").checked;
    const useLower = document.getElementById("pw-lower").checked;
    const useNumbers = document.getElementById("pw-numbers").checked;
    const useSymbols = document.getElementById("pw-symbols").checked;

    let chars = "";
    if (useUpper) chars += "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    if (useLower) chars += "abcdefghijklmnopqrstuvwxyz";
    if (useNumbers) chars += "0123456789";
    if (useSymbols) chars += "!@#$%^&*()_+-=[]{}|;:,.<>?";

    if (!chars) {
        showResult("Select at least one option!");
        return;
    }

    let password = "";
    const array = new Uint32Array(length);
    crypto.getRandomValues(array);
    for (let i = 0; i < length; i++) {
        password += chars[array[i] % chars.length];
    }
    showResult(password);
}

function doQRCode() {
    const input = document.getElementById("qr-input").value;
    if (!input) return;
    const url =
        "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" +
        encodeURIComponent(input);
    showResultHTML(
        `<img src="${url}" alt="QR Code" style="max-width:100%;border-radius:8px;">` +
        `<p style="margin-top:8px;font-family:monospace;font-size:12px;word-break:break-all;">${input}</p>`
    );
}

function doJsonFormat() {
    const input = document.getElementById("json-input").value;
    try {
        const parsed = JSON.parse(input);
        showResult(JSON.stringify(parsed, null, 2));
    } catch (e) {
        showResult("Invalid JSON:\n" + e.message);
    }
}

function doColorCopy() {
    const color = document.getElementById("cp-input").value;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(color);
    }
    showResult("Copied: " + color);
}

function doLorem() {
    const count = parseInt(document.getElementById("lorem-count").value) || 3;
    const paragraphs = [
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
        "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
        "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.",
        "Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt.",
        "Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem.",
        "Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur.",
        "Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur.",
    ];
    let result = "";
    for (let i = 0; i < count; i++) {
        result += paragraphs[i % paragraphs.length] + "\n\n";
    }
    showResult(result.trim());
}

// Close modal on backdrop click
document.getElementById("tool-modal")?.addEventListener("click", function (e) {
    if (e.target === this) closeModal();
});
