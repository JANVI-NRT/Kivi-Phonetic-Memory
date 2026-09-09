async function learnMemory() {
    const spokenForm = document.getElementById("spokenForm").value.trim();
    const preferredForm = document.getElementById("preferredForm").value.trim();
    const context = document.getElementById("context").value.trim();
    const language = document.getElementById("language").value.trim();

    const result = document.getElementById("learnResult");

    if (!spokenForm || !preferredForm) {
        result.textContent = "Enter both spoken and preferred forms.";
        return;
    }

    try {
        const response = await fetch("/memories", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                spoken_form: spokenForm,
                preferred_form: preferredForm,
                context: context || null,
                language: language || "en-us"
            })
        });

        const data = await response.json();

        if (!response.ok) {
            result.textContent =
                "Error: " + (data.detail || "Could not save memory");
            return;
        }

        result.textContent =
            `Learned: ${data.spoken_form} → ${data.preferred_form}`;

        document.getElementById("spokenForm").value = "";
        document.getElementById("preferredForm").value = "";
        document.getElementById("context").value = "";

        await loadMemories();
        await loadCandidates();

    } catch (error) {
        result.textContent = "Error: Could not connect to server.";
        console.error(error);
    }
}


async function loadMemories() {
    try {
        const response = await fetch("/memories");
        const memories = await response.json();

        const container = document.getElementById("memoryList");

        if (!response.ok) {
            container.innerHTML = "<p>Could not load memories.</p>";
            return;
        }

        if (memories.length === 0) {
            container.innerHTML = "<p>No memories stored.</p>";
            return;
        }

        container.innerHTML = memories.map(memory => `
            <div class="memory-item">
                <strong>${memory.spoken_form}</strong>
                →
                <strong>${memory.preferred_form}</strong>
                <br>
                <small>
                    Context: ${memory.context || "—"} |
                    Language: ${memory.language || "—"} |
                    Confidence: ${memory.confidence.toFixed(2)} |
                    Evidence: ${memory.evidence_count}
                </small>
            </div>
        `).join("");

    } catch (error) {
        document.getElementById("memoryList").innerHTML =
            "<p>Could not load memories.</p>";
        console.error(error);
    }
}


async function loadCandidates() {
    try {
        const response = await fetch("/candidates");
        const candidates = await response.json();

        const container = document.getElementById("candidateList");

        if (!response.ok || candidates.length === 0) {
            container.innerHTML = "<p>No candidates yet.</p>";
            return;
        }

        container.innerHTML = candidates.map(candidate => `
            <div class="memory-card">
                <strong>
                    ${candidate.observed_form}
                    →
                    ${candidate.possible_preferred_form}
                </strong>
                <div>Evidence: ${candidate.evidence_type}</div>
                <div>Confidence: ${candidate.confidence}</div>
                <div>Evidence count: ${candidate.evidence_count}</div>
                <div>Status: ${candidate.status}</div>
            </div>
        `).join("");

    } catch (error) {
        document.getElementById("candidateList").innerHTML =
            "<p>Could not load candidates.</p>";
        console.error(error);
    }
}


async function formatText() {
    const asrText = document.getElementById("asrText").value;
    const formattedText = document.getElementById("formattedText").value;

    try {
        const response = await fetch("/format", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                asr_text: asrText,
                formatted_text: formattedText
            })
        });

        const data = await response.json();

        if (!response.ok) {
            document.getElementById("memoryAwareText").textContent =
                "Error: " + (data.detail || "Formatting failed");
            return;
        }

        document.getElementById("memoryAwareText").textContent =
            data.memory_aware_text;

        showDecisions(data);

    } catch (error) {
        document.getElementById("memoryAwareText").textContent =
            "Error: Could not connect to server.";
        console.error(error);
    }
}


function showDecisions(data) {
    const container = document.getElementById("decisions");

    if (!data.trace || data.trace.length === 0) {
        container.innerHTML = "<p>No tokens were analyzed.</p>";
        return;
    }

    container.innerHTML = data.trace.map(item => `
        <div class="decision">
            <strong>${item.observed_form}</strong>
            <br>
            Decision:
            <strong>${item.decision}</strong>
            <br>
            Similarity: ${item.similarity_score}
            <br>
            Confidence: ${item.confidence}
            <br>
            Reason: ${item.reason}
        </div>
    `).join("");
}


async function resetMemories() {
    try {
        const response = await fetch("/memories/reset", {
            method: "POST"
        });

        const data = await response.json();

        document.getElementById("resetResult").textContent =
            data.message;

        await loadMemories();
        await loadCandidates();

    } catch (error) {
        document.getElementById("resetResult").textContent =
            "Error: Could not reset memories.";
        console.error(error);
    }
}


window.learnMemory = learnMemory;
window.loadMemories = loadMemories;
window.loadCandidates = loadCandidates;
window.formatText = formatText;
window.resetMemories = resetMemories;

window.addEventListener("DOMContentLoaded", () => {
    loadMemories();
    loadCandidates();
});
