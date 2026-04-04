#include "ThemeManager.h"
#include "WavyTheme.h"
#include "LmmsStyle.h"
#include <QAbstractScrollArea>
#include <QApplication>
#include <QFile>
#include <QPalette>
#include <QResizeEvent>
#include <QSettings>
#include <QStringList>
#include <QTimer>
#include <QWidget>

namespace Wavy {

static const char kThemeKey[] = "theme";
static const char kDefaultTheme[] = "wavy-orangesicle";

// Captured once on first call — LMMS's own stylesheet (LmmsStyle::LmmsStyle() output).
// We always prepend it so LMMS's lmms--gui--* class rules (TrackContentWidget grid
// colours, PianoRoll, SongEditor etc.) remain in effect.
static QString s_lmmsBaseStyle;
static WavyTheme* s_wavyTheme = nullptr;

// ── Per-theme color table ────────────────────────────────────────────────────
// All theme colors are defined once here and used by QPalette, WavyTheme,
// track-row overrides, and sidebar styling.

struct ThemeDef {
    const char* id;

    // QPalette roles
    const char* window;
    const char* windowText;
    const char* base;
    const char* altBase;
    const char* text;
    const char* button;
    const char* buttonText;
    const char* highlight;
    const char* highlightedText;
    const char* mid;
    const char* dark;
    const char* light;
    const char* shadow;
    const char* brightText;
    const char* disabled;       // disabled text/window color

    // WavyTheme (QML) — semantic colors (may differ from QPalette equivalents)
    const char* qmlBg;          // often == window but can differ
    const char* qmlSurface;     // often == base but can differ
    const char* fg;
    const char* dim;
    const char* outline;
    const char* errorBg;
    const char* userBg;
    const char* wavyBg;

    // Track row overrides
    const char* trackRowBg;
    const char* trackSidebarBg;

    // Sidebar styling
    const char* sidebarBg;
    const char* sidebarBtnBg;
    const char* sidebarBtnHover;
    const char* sidebarText;
    const char* sidebarAccentBg;
    const char* sidebarCheckedBg;
};

static const ThemeDef kThemes[] = {
    // ── wavy-crimson ──
    { "wavy-crimson",
      "#F6F6F6", "#1C1A1A", "#DEDEDE", "#EBEBEB", "#1C1A1A",
      "#D2D2D2", "#1C1A1A", "#C0392B", "#FFFFFF",
      "#BEBCBC", "#D2D2D2", "#FFFFFF", "#888080", "#4afd85",
      "#BEBCBC",
      "#F6F6F6", "#DEDEDE",  // qmlBg, qmlSurface
      "#1C1A1A", "#706B6B", "#BEBCBC", "#FCEAEA", "#DCE8F5", "#DFF2E8",
      "#F6F6F6", "#222020",
      "#F0D0D0", "#E8BEBE", "#DDB0B0", "#5A2020",
      "rgba(200,80,80,0.18)", "rgba(200,80,80,0.22)" },

    // ── wavy-silver ──
    { "wavy-silver",
      "#f4f2f2", "#221e1e", "#eeecec", "#e8e5e5", "#221e1e",
      "#d4d0d0", "#1a1717", "#c0392b", "#ffffff",
      "#bcb8b8", "#9a9696", "#fdfbfb", "#888484", "#4afd85",
      "#9a9696",
      "#f4f2f2", "#e8e4e4",  // qmlBg, qmlSurface (surface differs from base)
      "#1a1717", "#6e6464", "#b0acac", "#fceaea", "#dce8f5", "#dff2e8",
      "#f4f2f2", "#2a2020",
      "#ECDCDC", "#E0CCCC", "#D4BEBE", "#5A2020",
      "rgba(160,60,60,0.15)", "rgba(160,60,60,0.20)" },

    // ── wavy-ruby ──
    { "wavy-ruby",
      "#1a0a0a", "#f5e8e8", "#2e1515", "#231010", "#f5e8e8",
      "#3a1818", "#f5e8e8", "#e74c3c", "#ffffff",
      "#5a2020", "#3d1c1c", "#2e1515", "#0a0000", "#4afd85",
      "#5a2020",
      "#1a0a0a", "#2e1515",  // qmlBg, qmlSurface
      "#f5e8e8", "#c09090", "#5a2020", "#3d1515", "#1a2030", "#1a2e1a",
      "#1a0a0a", "#1a0a0a",
      "#3c1818", "#4a2222", "#5a2c2c", "#f0b8b0",
      "rgba(240,184,176,0.12)", "rgba(240,184,176,0.18)" },

    // ── wavy-midnight ──
    { "wavy-midnight",
      "#0d0d1a", "#e0deff", "#1e1e3c", "#141428", "#e0deff",
      "#282850", "#e0deff", "#7c3aed", "#ffffff",
      "#3d3d70", "#282850", "#1e1e3c", "#07070f", "#4af085",
      "#3d3d70",
      "#0d0d1a", "#1e1e3c",  // qmlBg, qmlSurface
      "#e0deff", "#9090c0", "#3d3d70", "#2d1b3d", "#1e2040", "#1a1e30",
      "#0d0d1a", "#0d0d1a",
      "#201840", "#2a2250", "#342c60", "#c8b8f0",
      "rgba(200,184,240,0.12)", "rgba(200,184,240,0.18)" },

    // ── wavy-orangesicle ──
    { "wavy-orangesicle",
      "#F9F8F6", "#1E1B18", "#E7E3DE", "#F0EDEA", "#1E1B18",
      "#DDD8D2", "#1E1B18", "#D4736C", "#FFFFFF",
      "#CCC7C0", "#B8B4AE", "#FFFFFF", "#8A857E", "#4afd85",
      "#CCC7C0",
      "#F9F8F6", "#E7E3DE",  // qmlBg, qmlSurface
      "#1E1B18", "#807A73", "#CCC7C0", "#FCE8E6", "#EEF2F8", "#EDF5EC",
      "#F0EDEA", "#E8E2DE",
      "#E8E2DE", "#DED6D0", "#D4CBC4", "#4A3E38",
      "rgba(212,115,108,0.18)", "rgba(212,115,108,0.22)" },

    // ── wavy-sunset ──
    { "wavy-sunset",
      "#0E0C18", "#EDE8F8", "#211D3A", "#17142A", "#EDE8F8",
      "#2E2850", "#EDE8F8", "#E8834A", "#FFFFFF",
      "#463E6E", "#2E2850", "#211D3A", "#05030E", "#4afd85",
      "#463E6E",
      "#0E0C18", "#211D3A",  // qmlBg, qmlSurface
      "#EDE8F8", "#8878A8", "#463E6E", "#2A1A30", "#1A1A30", "#1A2418",
      "#0E0C18", "#0E0C18",
      "#281838", "#322044", "#3c2a50", "#d8b0e0",
      "rgba(216,176,224,0.12)", "rgba(216,176,224,0.18)" },
};

static const int kThemeCount = sizeof(kThemes) / sizeof(kThemes[0]);
static const int kSilverIdx  = 1;  // index of wavy-silver (fallback)

static const ThemeDef& findTheme(const QString& id) {
    for (int i = 0; i < kThemeCount; ++i)
        if (id == QLatin1String(kThemes[i].id))
            return kThemes[i];
    return kThemes[kSilverIdx];
}

// ── ThemeManager implementation ──────────────────────────────────────────────

WavyTheme* ThemeManager::themeObject()
{
    if (!s_wavyTheme)
        s_wavyTheme = new WavyTheme();
    return s_wavyTheme;
}

QString ThemeManager::currentTheme()
{
    QSettings s;
    s.beginGroup("Wavy");
    QString id = s.value(kThemeKey, kDefaultTheme).toString();
    s.endGroup();
    return id;
}

void ThemeManager::applyTheme(const QString& id)
{
    // Capture LMMS base style on first call (empty in standalone/non-LMMS builds).
    if (s_lmmsBaseStyle.isNull())
        s_lmmsBaseStyle = qApp->styleSheet();

    QString wavyQSS;
    QString path = QString(":/themes/%1/style.qss").arg(id);
    QFile file(path);
    if (file.open(QFile::ReadOnly)) {
        wavyQSS = QString::fromUtf8(file.readAll());
    } else {
        // Fallback to default theme
        QFile fallback(QString(":/themes/%1/style.qss").arg(kDefaultTheme));
        if (fallback.open(QFile::ReadOnly))
            wavyQSS = QString::fromUtf8(fallback.readAll());
    }

    // Track which palette to use: if file wasn't found, we fell back to silver
    const bool fileFound = file.isOpen();
    const QString effectiveId = fileFound ? id : QLatin1String("wavy-silver");
    const ThemeDef& t = findTheme(effectiveId);

    // Append Wavy QSS after LMMS base so our rules win on equal-specificity conflicts
    // but LMMS's namespaced class rules (lmms--gui--*) survive and keep widgets themed.
    qApp->setStyleSheet(s_lmmsBaseStyle + QLatin1String("\n/* ==wavy== */\n") + wavyQSS);

    // Apply QPalette so palette-painting widgets (TrackOperationsWidget, editors, etc.)
    // pick up our colors. This runs after GuiApplication so it overrides LmmsStyle.
    {
        QPalette pal;
        pal.setColor(QPalette::Window,          QColor(t.window));
        pal.setColor(QPalette::WindowText,      QColor(t.windowText));
        pal.setColor(QPalette::Base,            QColor(t.base));
        pal.setColor(QPalette::AlternateBase,   QColor(t.altBase));
        pal.setColor(QPalette::Text,            QColor(t.text));
        pal.setColor(QPalette::Button,          QColor(t.button));
        pal.setColor(QPalette::ButtonText,      QColor(t.buttonText));
        pal.setColor(QPalette::Highlight,       QColor(t.highlight));
        pal.setColor(QPalette::HighlightedText, QColor(t.highlightedText));
        pal.setColor(QPalette::Mid,             QColor(t.mid));
        pal.setColor(QPalette::Dark,            QColor(t.dark));
        pal.setColor(QPalette::Light,           QColor(t.light));
        pal.setColor(QPalette::Shadow,          QColor(t.shadow));
        pal.setColor(QPalette::BrightText,      QColor(t.brightText));
        const QColor disabledClr(t.disabled);
        pal.setColor(QPalette::Disabled, QPalette::Window,     disabledClr);
        pal.setColor(QPalette::Disabled, QPalette::WindowText, disabledClr);
        pal.setColor(QPalette::Disabled, QPalette::Text,       disabledClr);
        pal.setColor(QPalette::Disabled, QPalette::ButtonText, disabledClr);
        qApp->setPalette(pal);

        // Sync LmmsStyle::s_palette so standardPalette() returns our themed
        // palette — this fixes palette-painting widgets (TrackOperationsWidget, etc.)
        if (lmms::gui::LmmsStyle::s_palette) {
            *lmms::gui::LmmsStyle::s_palette = pal;
        }
    }

    // Update QML theme object so reactive bindings re-render automatically
    themeObject()->apply(
        QColor(t.qmlBg),
        QColor(t.qmlSurface),
        QColor(t.highlight), // accent  (== QPalette::Highlight)
        QColor(t.fg),
        QColor(t.dim),
        QColor(t.outline),
        QColor(t.errorBg),
        QColor(t.userBg),
        QColor(t.wavyBg)
    );

    // LMMS's TrackContentWidget caches its grid into a QPixmap (m_background) and
    // only regenerates it on resizeEvent or snap changes.  After a stylesheet swap
    // the qproperty setters are called but the pixmap is stale.  A zero-pixel resize
    // nudge flushes every TrackContentWidget through resizeEvent → updateBackground().
    //
    // TrackView::TrackView() hardcodes QPalette::Window = QColor(32,36,40) via
    // setPalette(), overriding both qApp->setPalette() and QSS.  We must reset it
    // here, after all widgets have been constructed.
    // TrackOperationsWidget::paintEvent uses palette().brush(QPalette::Window) and
    // inherits from TrackView — we override it separately so the sidebar stays dark.
    const QColor trackRowBgC(t.trackRowBg);
    const QColor trackSidebarBgC(t.trackSidebarBg);
    QTimer::singleShot(0, qApp, [effectiveId, trackRowBgC, trackSidebarBgC]() {
        // ── Sidebar inline stylesheet (for live theme switches) ─────────
        // On startup, WavyShell::adoptLmmsContent() calls applySidebarStyle()
        // directly. This handles live theme changes via setTheme().
        {
            const auto allW = QApplication::allWidgets();
            for (QWidget* w : allW) {
                if (w->objectName() == "WavySideBar") {
                    applySidebarStyle(w, effectiveId);
                    break;
                }
            }
        }

        // ── Track row / sidebar palette overrides ──────────────────────
        const QColor& trackRowBg = trackRowBgC;
        const QColor& trackSidebarBg = trackSidebarBgC;

        const auto allWidgets = QApplication::allWidgets();
        for (QWidget* w : allWidgets) {
            const char* cn = w->metaObject()->className();

            if (qstrcmp(cn, "lmms::gui::TrackContentWidget") == 0) {
                // Flush cached grid pixmap via fake resize
                QResizeEvent fakeResize(w->size(), w->size());
                QApplication::sendEvent(w, &fakeResize);

            } else if (
                qstrcmp(cn, "lmms::gui::TrackView") == 0 ||
                qstrcmp(cn, "lmms::gui::InstrumentTrackView") == 0 ||
                qstrcmp(cn, "lmms::gui::SampleTrackView") == 0 ||
                qstrcmp(cn, "lmms::gui::PatternTrackView") == 0 ||
                qstrcmp(cn, "lmms::gui::AutomationTrackView") == 0 ||
                qstrcmp(cn, "lmms::gui::BBTrackView") == 0
            ) {
                // Override the hardcoded QColor(32,36,40) set in TrackView's ctor
                QPalette pal = w->palette();
                pal.setColor(QPalette::Window, trackRowBg);
                pal.setColor(QPalette::Base,   trackRowBg);
                w->setPalette(pal);
                w->update();

            } else if (qstrcmp(cn, "lmms::gui::TrackOperationsWidget") == 0) {
                // paintEvent: p.fillRect(rect(), palette().brush(QPalette::Window))
                // Force the dark sidebar color independent of the parent TrackView
                QPalette pal = w->palette();
                pal.setColor(QPalette::Window, trackSidebarBg);
                w->setPalette(pal);
                w->update();

            } else if (qstrcmp(cn, "lmms::gui::TrackContainerView") == 0) {
                // Force viewport to paint QSS background-color
                // (autoFillBackground=false by default)
                for (QObject* child : w->children()) {
                    if (auto* sa = qobject_cast<QAbstractScrollArea*>(child)) {
                        sa->viewport()->setAutoFillBackground(true);
                        sa->viewport()->update();
                    }
                }
            }
        }
    });
}

void ThemeManager::applySidebarStyle(QWidget* sidebar, const QString& themeId)
{
    if (!sidebar) return;

    const ThemeDef& t = findTheme(themeId);

    sidebar->setStyleSheet(QString(
        "QToolBar#WavySideBar { background-color: %1; border: none;"
        "  padding: 0px; margin: 0px; }"
        // AI nav buttons — icon-only, centered
        "QToolButton#WavyAINavBtn {"
        "  background-color: transparent; color: %4;"
        "  border: none; border-radius: 0px; padding: 0px;"
        "  margin: 0px; min-height: 36px; }"
        "QToolButton#WavyAINavBtn:hover {"
        "  background-color: %5; }"
        "QToolButton#WavyAINavBtn:checked {"
        "  background-color: %6; }"
        // LMMS editor buttons
        "QToolBar#WavySideBar QToolButton {"
        "  background-color: %2; color: %4;"
        "  border: none; border-radius: 0px; padding: 0px;"
        "  margin: 0px; }"
        "QToolBar#WavySideBar QToolButton:hover {"
        "  background-color: %3; }"
        "QToolBar#WavySideBar QToolButton:checked {"
        "  background-color: %3; }"
    ).arg(
        QLatin1String(t.sidebarBg),
        QLatin1String(t.sidebarBtnBg),
        QLatin1String(t.sidebarBtnHover),
        QLatin1String(t.sidebarText),
        QLatin1String(t.sidebarAccentBg),
        QLatin1String(t.sidebarCheckedBg)
    ));
}

void ThemeManager::setTheme(const QString& id)
{
    QSettings s;
    s.beginGroup("Wavy");
    s.setValue(kThemeKey, id);
    s.endGroup();
    applyTheme(id);
}

QStringList ThemeManager::availableThemes()
{
    return { "wavy-crimson", "wavy-silver", "wavy-ruby", "wavy-midnight", "wavy-orangesicle", "wavy-sunset" };
}

} // namespace Wavy
