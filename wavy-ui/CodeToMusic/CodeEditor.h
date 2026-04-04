#pragma once
#include <QWidget>
#ifdef WAVY_WEBENGINE
#  include <QWebEngineView>
#endif
#include <QComboBox>
#include <QPushButton>
#include <QLabel>
#include <QProgressBar>
#include <QListWidget>
#include <QVariantMap>
#include <QSplitter>

class AIClient;

// ---------------------------------------------------------------------------
// CodeEditor — Monaco editor embedded via QWebEngineView for Code-to-Music.
// Supports DSL, Python, CSV, and JSON input modes.
// ---------------------------------------------------------------------------

class CodeEditor : public QWidget
{
    Q_OBJECT
public:
    explicit CodeEditor(AIClient* client, QWidget* parent = nullptr);

Q_SIGNALS:
    void tracksReady(const QVariantList& trackDefs,
                     const QString& midiPath,
                     const QStringList& audioPaths);

private Q_SLOTS:
    void onRunClicked();
    void onConvertFinished(bool ok, const QVariantMap& result);
    void onEditorLoaded(bool ok);
    void onModeChanged(int index);

private:
    void buildUI();
    void loadMonacoEditor();
    void setCode(const QString& code);
    void setRunning(bool busy);

    AIClient*        m_client{nullptr};
#ifdef WAVY_WEBENGINE
    QWebEngineView*  m_editor{nullptr};
#else
    QWidget*         m_editor{nullptr};
#endif
    QComboBox*       m_modeCombo{nullptr};
    QPushButton*     m_runBtn{nullptr};
    QProgressBar*    m_progress{nullptr};
    QListWidget*     m_outputList{nullptr};
    QLabel*          m_statusLabel{nullptr};

    static constexpr const char* DSL_EXAMPLE = R"(
# Wavy Labs DSL example
tempo(128)
key("C minor")

track("drums").pattern([1,0,0,1, 0,0,1,0, 1,0,0,1, 0,0,1,0], bpm=128)
track("bass").melody(["C2","G2","Bb2","C3","Eb3"], duration="eighth")
track("synth").generate("lush ambient pad, C minor", key="C minor")
)";

    static constexpr const char* PYTHON_EXAMPLE = R"(
# Python code-to-music example
track("drums").pattern([1,0,0,1,0,0,1,0], bpm=140)
track("bass").melody([C3, E3, G3, C4], duration="quarter")
track("synth").generate("ambient pad", key="C minor")
)";
};
