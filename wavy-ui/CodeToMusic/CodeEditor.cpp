#include "CodeEditor.h"
#include "../IPC/AIClient.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGroupBox>
#include <QSplitter>
#include <QWebEngineView>
#include <QWebEngineSettings>
#include <QJsonDocument>
#include <QJsonObject>
#include <QListWidgetItem>
#include <QFile>
#include <QFileInfo>

// ---------------------------------------------------------------------------
// Monaco editor HTML (CDN-loaded; bundled fallback path is in resources.qrc)
// ---------------------------------------------------------------------------

static const QString MONACO_HTML = R"(
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d0d14; }
  #container { width:100vw; height:100vh; }
</style>
</head>
<body>
<div id="container"></div>
<script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.47.0/min/vs/loader.js"></script>
<script>
require.config({ paths: { 'vs': 'https://cdn.jsdelivr.net/npm/monaco-editor@0.47.0/min/vs' } });
require(['vs/editor/editor.main'], function() {
    window.editor = monaco.editor.create(document.getElementById('container'), {
        value: '',
        language: 'python',
        theme: 'vs-dark',
        fontSize: 13,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    });
    // Signal C++ that the editor is ready
    if (window.qt && window.qt.webChannelTransport) {
        new QWebChannel(window.qt.webChannelTransport, function(ch) {
            window.wavyBridge = ch.objects.bridge;
        });
    }
});
function getCode() { return window.editor ? window.editor.getValue() : ''; }
function setCode(c) { if (window.editor) window.editor.setValue(c); }
function setLanguage(lang) {
    if (window.editor)
        monaco.editor.setModelLanguage(window.editor.getModel(), lang);
}
</script>
</body>
</html>
)";

// ---------------------------------------------------------------------------

CodeEditor::CodeEditor(AIClient* client, QWidget* parent)
    : QWidget(parent), m_client(client)
{
    buildUI();
}

void CodeEditor::buildUI()
{
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    // ── Toolbar ───────────────────────────────────────────────────────────
    auto* toolbar = new QWidget(this);
    toolbar->setObjectName("codeEditorToolbar");
    auto* tl = new QHBoxLayout(toolbar);
    tl->setContentsMargins(12, 6, 12, 6);
    tl->setSpacing(8);

    auto* modeLabel = new QLabel("Mode:", toolbar);
    m_modeCombo = new QComboBox(toolbar);
    m_modeCombo->addItem("Wavy DSL",    "dsl");
    m_modeCombo->addItem("Python",      "python");
    m_modeCombo->addItem("CSV Data",    "csv");
    m_modeCombo->addItem("JSON Data",   "json_data");
    connect(m_modeCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &CodeEditor::onModeChanged);

    m_runBtn = new QPushButton("▶  Run", toolbar);
    m_runBtn->setObjectName("codeRunBtn");
    m_runBtn->setFixedWidth(80);
    connect(m_runBtn, &QPushButton::clicked, this, &CodeEditor::onRunClicked);

    m_statusLabel = new QLabel(toolbar);
    m_statusLabel->setObjectName("codeStatusLabel");

    auto* studioNote = new QLabel("Studio tier", toolbar);
    studioNote->setObjectName("tierBadgeStudio");

    tl->addWidget(modeLabel);
    tl->addWidget(m_modeCombo);
    tl->addStretch();
    tl->addWidget(m_statusLabel);
    tl->addWidget(m_runBtn);
    tl->addWidget(studioNote);
    root->addWidget(toolbar);

    // ── Splitter: editor | output ─────────────────────────────────────────
    auto* splitter = new QSplitter(Qt::Vertical, this);

    m_editor = new QWebEngineView(splitter);
    m_editor->settings()->setAttribute(
        QWebEngineSettings::JavascriptEnabled, true);
    connect(m_editor, &QWebEngineView::loadFinished,
            this, &CodeEditor::onEditorLoaded);
    loadMonacoEditor();
    splitter->addWidget(m_editor);

    // Output panel
    auto* outPanel = new QWidget(splitter);
    auto* opl = new QVBoxLayout(outPanel);
    opl->setContentsMargins(8, 4, 8, 4);
    auto* outHeader = new QLabel("Output Tracks", outPanel);
    outHeader->setObjectName("sectionHeader");
    opl->addWidget(outHeader);
    m_outputList = new QListWidget(outPanel);
    opl->addWidget(m_outputList);
    splitter->addWidget(outPanel);
    splitter->setSizes({320, 160});

    root->addWidget(splitter, 1);

    // Progress
    m_progress = new QProgressBar(this);
    m_progress->setRange(0, 0);
    m_progress->setVisible(false);
    m_progress->setMaximumHeight(4);
    root->addWidget(m_progress);
}

void CodeEditor::loadMonacoEditor()
{
    m_editor->setHtml(MONACO_HTML, QUrl("about:blank"));
}

void CodeEditor::onEditorLoaded(bool ok)
{
    if (!ok) return;
    const int idx = m_modeCombo->currentIndex();
    const QString example = (idx == 0) ? QString(DSL_EXAMPLE) : QString(PYTHON_EXAMPLE);
    setCode(example);
}

void CodeEditor::onModeChanged(int index)
{
    const QStringList langs = {"python", "python", "plaintext", "json"};
    const QString lang = langs.value(index, "python");
    m_editor->page()->runJavaScript(
        QString("setLanguage('%1');").arg(lang));

    if (index == 0) setCode(DSL_EXAMPLE);
    else if (index == 1) setCode(PYTHON_EXAMPLE);
}

void CodeEditor::setCode(const QString& code)
{
    const QString escaped = code.toHtmlEscaped()
        .replace("'", "\\'").replace("\n", "\\n");
    m_editor->page()->runJavaScript(
        QString("setCode('%1');").arg(escaped));
}

void CodeEditor::onRunClicked()
{
    setRunning(true);
    m_outputList->clear();

    m_editor->page()->runJavaScript("getCode();",
        [this](const QVariant& codeVar) {
            const QString code = codeVar.toString();
            const QString mode = m_modeCombo->currentData().toString();

            QVariantMap params;
            params["code"] = code;
            params["mode"] = mode;

            m_client->codeToMusic(params,
                [this](bool ok, const QVariantMap& result) {
                    QMetaObject::invokeMethod(this, [this, ok, result]() {
                        onConvertFinished(ok, result);
                    }, Qt::QueuedConnection);
                });
        });
}

void CodeEditor::onConvertFinished(bool ok, const QVariantMap& result)
{
    setRunning(false);
    if (!ok) {
        m_statusLabel->setText("⚠ " + result.value("error").toString());
        return;
    }

    const QString     midiPath   = result.value("midi_path").toString();
    const QVariantList tracks    = result.value("track_defs").toList();
    const QVariantList audioVar  = result.value("audio_paths").toList();

    // Collect audio paths as QStringList for the signal
    QStringList audioPaths;
    for (const QVariant& ap : audioVar)
        audioPaths << ap.toString();

    m_outputList->addItem("\U0001f3b5 MIDI: " + midiPath);
    for (const QVariant& t : tracks) {
        const QVariantMap tm = t.toMap();
        m_outputList->addItem(
            QString("  \u2713  Track: %1 (%2)")
                .arg(tm.value("track").toString(),
                     tm.value("type").toString()));
    }
    for (const QString& ap : audioPaths) {
        m_outputList->addItem(
            QString("  \U0001f3a7  Audio: %1")
                .arg(QFileInfo(ap).fileName()));
    }

    m_statusLabel->setText(QString("\u2713  %1 tracks").arg(tracks.size()));
    emit tracksReady(tracks, midiPath, audioPaths);
}

void CodeEditor::setRunning(bool busy)
{
    m_progress->setVisible(busy);
    m_runBtn->setEnabled(!busy);
    m_runBtn->setText(busy ? "⏳ Running …" : "▶  Run");
}
