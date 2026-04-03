#pragma once

#ifdef WAVY_LMMS_CORE

#include <QList>
#include <QMainWindow>
#include <QMap>
#include <QMdiSubWindow>
#include <QRect>
#include <QDockWidget>
#include <QStackedWidget>

class EngineAPI;
class TransportBar;
class AIBackend;
class WavyArrangementView;
class WavyPianoRollBar;
class QSplitter;
class QToolButton;
class QPushButton;
class QWidget;

namespace lmms::gui {
    class MainWindow;
}

// ---------------------------------------------------------------------------
// WavyShell — top-level window replacing LMMS's MDI desktop with a modern
// single-window layout: editor tab bar + docked panels.
//
// Strategy:
//   1. GuiApplication creates LMMS MainWindow + editors as normal.
//   2. WavyShell takes MainWindow's central widget (sidebar + workspace)
//      and uses it as its own central content.
//   3. Editor switching uses a tab bar that calls MainWindow's toggle slots.
//   4. MainWindow stays alive (hidden) so all LMMS internal references work.
// ---------------------------------------------------------------------------

class WavyShell : public QMainWindow
{
    Q_OBJECT

public:
    explicit WavyShell(EngineAPI* engine, QWidget* parent = nullptr);

    /// Call after GuiApplication creates everything.
    /// Reparents LMMS content into WavyShell and hides the LMMS MainWindow.
    void adoptLmmsContent(lmms::gui::MainWindow* lmmsWin);

    /// Access the LMMS MainWindow (kept alive for internal references).
    lmms::gui::MainWindow* lmmsMainWindow() const { return m_lmmsWin; }

    /// Dock a widget (e.g. AI panel) on the right side of the shell.
    void setAIPanel(QWidget* panel);

    /// Add G/V/S/M/T/C/A/L nav buttons to the LMMS left sidebar.
    /// Call after adoptLmmsContent() + setAIPanel().
    void addAINavButtons(AIBackend* backend);

    /// Re-hide stale MDI subwindows and maximize Song Editor.
    /// Call after operations (e.g. createNewProject) that may re-show hidden windows.
    void cleanupMdiWindows();

    /// Set the dashboard landing page widget (shown at launch, Home tab).
    /// Call after adoptLmmsContent().
    void setDashboard(QWidget* dash);

    /// Programmatically switch to a given editor tab index (0=Home, 1=Song, etc.).
    void activateEditorTab(int idx);

    /// Access the arrangement view.
    WavyArrangementView* arrangementView() const { return m_arrangementView; }

protected:
    void closeEvent(QCloseEvent* event) override;
    bool eventFilter(QObject* obj, QEvent* e) override;

private slots:
    void onEditorTabClicked(int index);
    void onSubWindowActivated(QMdiSubWindow* sub);

private:
    void buildEditorTabs();
void tileVisibleEditors();
    void setAIPanelVisible(bool visible);

    EngineAPI* m_engine;
    TransportBar* m_transport{nullptr};
    WavyArrangementView* m_arrangementView{nullptr};
    QList<QToolButton*> m_aiNavButtons;
    WavyPianoRollBar* m_pianoRollBar{nullptr};
    QWidget*        m_editorBar{nullptr};
    QList<QPushButton*> m_editorBtns;
    // Tiled subwindow geometry lock — prevents user dragging tiled panels
    QMap<QMdiSubWindow*, QRect> m_tiledGeoms;  // expected geometry per locked subwindow
    bool m_isTiling{false};                    // guard: suppresses event filter during our own setGeometry

    QWidget*        m_lmmsContent{nullptr};   // LMMS central widget (the horizontal splitter)
    QWidget*        m_aiPanel{nullptr};        // AI panel inserted in splitter (toggleable)
    QSplitter*      m_splitter{nullptr};       // cached splitter for resize on panel toggle
    int             m_aiPanelWidth{326};       // last known visible width of AI panel
    QWidget*        m_header{nullptr};         // Unified header: menu bar + transport
    QStackedWidget* m_workStack{nullptr};      // index 0: LMMS editors, index 1: dashboard
    lmms::gui::MainWindow* m_lmmsWin{nullptr};

    // Map tab index → editor widget pointer (for reverse lookup)
    enum EditorTab { Home = 0, Song, PianoRoll, Pattern, Automation, Mixer, TabCount };
};

#endif // WAVY_LMMS_CORE
