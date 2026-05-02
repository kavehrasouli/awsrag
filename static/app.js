const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const askButton = document.getElementById("ask-btn");
const clearButton = document.getElementById("clear-btn");
const questionInput = document.getElementById("q");
const uploadStatus = document.getElementById("upload-status");
const fileList = document.getElementById("file-list");
const resultDiv = document.getElementById("result");
const count = document.getElementById("count");

let hasDocuments = false;

dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (event) => uploadFiles(event.target.files));
clearButton.addEventListener("click", clearDocs);
askButton.addEventListener("click", ask);
questionInput.addEventListener("keypress", (event) => {
    if (event.key === "Enter") {
        ask();
    }
});

dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));

dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");

    const files = [...event.dataTransfer.files].filter((file) => file.type === "application/pdf");
    if (files.length === 0) {
        addStatus("Only PDF files are supported", "error");
        return;
    }

    uploadFiles(files);
});

function addStatus(message, type = "success") {
    const item = document.createElement("div");
    item.className = `status-item ${type}`;
    item.textContent = message;
    uploadStatus.appendChild(item);
}

function updateFileList(files) {
    if (files.length === 0) {
        fileList.textContent = "";
        return;
    }

    fileList.textContent = `Uploaded files: ${files.join(", ")}`;
}

function enableAsk() {
    hasDocuments = true;
    askButton.disabled = false;
    questionInput.placeholder = "Ask a question about your documents...";
}

function disableAsk() {
    hasDocuments = false;
    askButton.disabled = true;
    questionInput.placeholder = "Upload a PDF first, then ask questions about it...";
}

async function uploadFiles(files) {
    for (const file of files) {
        addStatus(`Uploading ${file.name}...`);

        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch("/upload", { method: "POST", body: formData });
            const data = await response.json();

            if (data.success) {
                addStatus(`Success: ${file.name} - added ${data.chunks} chunks`);
                count.textContent = data.total_docs;
                updateFileList(data.files);
                enableAsk();
            } else {
                addStatus(`Error: ${file.name} - ${data.error}`, "error");
            }
        } catch (error) {
            addStatus(`Error: ${file.name} - upload failed`, "error");
        }
    }

    fileInput.value = "";
}

async function clearDocs() {
    if (!confirm("Clear all uploaded documents?")) {
        return;
    }

    await fetch("/clear", { method: "POST" });
    count.textContent = "0";
    uploadStatus.textContent = "";
    fileList.textContent = "";
    resultDiv.style.display = "block";
    resultDiv.innerHTML = '<div class="empty-state">Upload a PDF to get started</div>';
    disableAsk();
    addStatus("Knowledge base cleared");
}

async function ask() {
    const question = questionInput.value;
    if (!question || !hasDocuments) {
        return;
    }

    resultDiv.style.display = "block";
    resultDiv.innerHTML = "<p>Searching and thinking...</p>";

    const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
    });
    const data = await response.json();

    resultDiv.replaceChildren();
    const answerHeading = document.createElement("h3");
    answerHeading.textContent = "Answer";
    const answer = document.createElement("p");
    answer.textContent = data.answer;
    const contextHeading = document.createElement("h4");
    contextHeading.textContent = "Retrieved Context";

    resultDiv.append(answerHeading, answer, contextHeading);
    data.sources.forEach((source) => {
        const preview = source.length > 300 ? `${source.substring(0, 300)}...` : source;
        const sourceDiv = document.createElement("div");
        sourceDiv.className = "doc";
        sourceDiv.textContent = `- ${preview}`;
        resultDiv.appendChild(sourceDiv);
    });
}
