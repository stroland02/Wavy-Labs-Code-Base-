#include "TransportBar.h"
#include "GenreConfigPopup.h"
#include "../EngineAPI/EngineAPI.h"
#include "../QML/AIBackend.h"
#include "../ThemeManager/ThemeManager.h"
#include "../QML/GenreModes.h"

#include <QComboBox>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPainter>
#include <QToolButton>
#include <QSpinBox>
#include <QTimer>
#include <QVBoxLayout>
#include <QMouseEvent>
#include <QWheelEvent>
#include <cmath>
#include <functional>

#ifdef WAVY_LMMS_CORE
#include "MainWindow.h"
#endif

// ---------------------------------------------------------------------------
// MiniKnob — compact QPainter rotary control (no Q_OBJECT, uses std::function)
// ---------------------------------------------------------------------------

class MiniKnob : public QWidget
{
public:
    MiniKnob(int minVal, int maxVal, int initVal, const QString& tip,
             std::function<void(int)> cb, QWidget* parent = nullptr)
        : QWidget(parent)
        , m_min(minVal), m_max(maxVal), m_value(initVal)
        , m_callback(std::move(cb))
    {
        setFixedSize(34, 34);
        setCursor(Qt::SizeVerCursor);
        setToolTip(tip);
    }

    int value() const { return m_value; }

    void setValue(int v)
    {
        v = qBound(m_min, v, m_max);
        if (v != m_value) { m_value = v; update(); }
    }

protected:
    void paintEvent(QPaintEvent*) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);

        const QRect   outer  = rect().adjusted(2, 2, -2, -2);
        const QRectF  arc    = QRectF(outer).adjusted(4, 4, -4, -4);
        const QPointF center(width() / 2.0, height() / 2.0);
        const double  t = (m_max > m_min)
            ? static_cast<double>(m_value - m_min) / (m_max - m_min) : 0.0;

        // Theme-adaptive colours
        auto* th = Wavy::ThemeManager::themeObject();
        const QColor accent  = th ? th->accent()  : QColor("#00e87a");
        const QColor outline = th ? th->outline() : QColor("#1a3020");

        // Near-black knob background, lightly tinted by accent
        const QColor knobBg = QColor(
            qMin(255, accent.red()   / 12 + 4),
            qMin(255, accent.green() / 12 + 4),
            qMin(255, accent.blue()  / 12 + 7));

        // Dim track: 28% of accent brightness
        const QColor dimTrack = QColor(
            qMin(255, int(accent.red()   * 0.28)),
            qMin(255, int(accent.green() * 0.28)),
            qMin(255, int(accent.blue()  * 0.28)));

        // Background circle
        p.setBrush(knobBg);
        p.setPen(QPen(outline, 1));
        p.drawEllipse(outer);

        // Full-range dim track (SW → SE, 270° span)
        p.setBrush(Qt::NoBrush);
        p.setPen(QPen(dimTrack, 2, Qt::SolidLine, Qt::RoundCap));
        p.drawArc(arc, 225 * 16, -270 * 16);

        // Value arc (accent colour)
        if (t > 0.0) {
            p.setPen(QPen(accent, 2, Qt::SolidLine, Qt::RoundCap));
            p.drawArc(arc, 225 * 16, static_cast<int>(-t * 270.0 * 16));
        }

        // Pointer: filled dot at tip position
        //   t=0 → 225° (SW),  t=1 → 315° (SE)
        const double angleDeg = 225.0 - t * 270.0;
        const double angleRad = angleDeg * M_PI / 180.0;
        const double rTip     = outer.width() / 2.0 - 4.0;
        const QPointF tipPt   = center + QPointF( rTip * std::cos(angleRad),
                                                  -rTip * std::sin(angleRad));
        p.setPen(Qt::NoPen);
        p.setBrush(accent);
        p.drawEllipse(tipPt, 2.5, 2.5);
    }

    void mousePressEvent(QMouseEvent* e) override
    {
        m_dragStart = e->pos();
        m_dragValue = m_value;
    }

    void mouseMoveEvent(QMouseEvent* e) override
    {
        const int dy      = m_dragStart.y() - e->pos().y();
        const int range   = m_max - m_min;
        const int newVal  = qBound(m_min, m_dragValue + dy * range / 120, m_max);
        if (newVal != m_value) {
            m_value = newVal;
            update();
            if (m_callback) m_callback(m_value);
        }
    }

    void wheelEvent(QWheelEvent* e) override
    {
        const int step   = (e->angleDelta().y() > 0) ? 1 : -1;
        const int newVal = qBound(m_min, m_value + step, m_max);
        if (newVal != m_value) {
            m_value = newVal;
            update();
            if (m_callback) m_callback(m_value);
        }
    }

private:
    int m_min, m_max, m_value;
    std::function<void(int)> m_callback;
    QPoint m_dragStart;
    int    m_dragValue{0};
};

// ---------------------------------------------------------------------------
// WavyLogoLabel — "WAVY LABS" with purple hover-glow effect
// (subclasses QLabel — no Q_OBJECT needed; QLabel already supplies it)
// ---------------------------------------------------------------------------

class WavyLogoLabel : public QLabel
{
public:
    explicit WavyLogoLabel(QWidget* parent = nullptr) : QLabel(parent)
    {
        setText("WAVY LABS");
        setAlignment(Qt::AlignCenter);
        setFixedWidth(120);
        setAttribute(Qt::WA_Hover, true);
        setMouseTracking(true);
        applyColor(0.0f);

        m_animTimer = new QTimer(this);
        m_animTimer->setInterval(16);   // ~60 fps
        connect(m_animTimer, &QTimer::timeout, this, [this]() {
            const float target = m_hovered ? 1.0f : 0.0f;
            if (std::abs(m_brightness - target) < 0.015f) {
                m_brightness = target;
                m_animTimer->stop();
            } else {
                m_brightness += (target - m_brightness) * 0.10f;
            }
            applyColor(m_brightness);
        });
    }

protected:
    void enterEvent(QEnterEvent* e) override
    {
        m_hovered = true;
        m_animTimer->start();
        QLabel::enterEvent(e);
    }

    void leaveEvent(QEvent* e) override
    {
        m_hovered = false;
        m_animTimer->start();
        QLabel::leaveEvent(e);
    }

private:
    void applyColor(float t)   // t = 0.0 (dark idle) .. 1.0 (full accent)
    {
        const QColor accent = Wavy::ThemeManager::themeObject()->accent();
        // Idle: very dark version of accent hue (22% value)
        const QColor idle = QColor::fromHsvF(
            accent.hueF(),
            qMin(1.0, accent.saturationF() * 0.80),
            qMax(0.15, accent.valueF() * 0.22)
        );
        const int r = idle.red()   + int((accent.red()   - idle.red())   * t);
        const int g = idle.green() + int((accent.green() - idle.green()) * t);
        const int b = idle.blue()  + int((accent.blue()  - idle.blue())  * t);
        setStyleSheet(QString(
            "color: %1;"
            " font-size: 17px;"
            " font-weight: 800;"
            " letter-spacing: 3px;"
            " background: transparent;").arg(QColor(r, g, b).name()));
    }

    QTimer* m_animTimer{nullptr};
    float   m_brightness{0.0f};
    bool    m_hovered{false};
};

// ---------------------------------------------------------------------------
// TransportBar
// ---------------------------------------------------------------------------

TransportBar::TransportBar(EngineAPI* engine, QWidget* parent)
    : QWidget(parent)
    , m_engine(engine)
{
    setObjectName("WavyTransportBar");
    setFixedHeight(44);
    setAttribute(Qt::WA_StyledBackground, true);  // honour QSS background: transparent
    buildUI();

    // Re-colour all display widgets when the user switches themes
    connect(Wavy::ThemeManager::themeObject(), &Wavy::WavyTheme::changed,
            this, &TransportBar::applyThemeColors);

    connect(m_engine, &EngineAPI::tempoChanged,
            this, [this](int bpm) {
                const QSignalBlocker b(m_bpmSpin);
                m_bpmSpin->setValue(bpm);
                m_bpmValueLabel->setText(QString::number(bpm));
            });

    connect(m_engine, &EngineAPI::masterVolumeChanged,
            this, [this](int vol) {
                m_volumeKnob->setValue(vol);
                m_volumeLabel->setText(QString::number(vol) + "%");
            });

    m_posTimer = new QTimer(this);
    m_posTimer->setInterval(100);
    connect(m_posTimer, &QTimer::timeout, this, &TransportBar::updatePosition);
    m_posTimer->start();
}

// ---------------------------------------------------------------------------

void TransportBar::buildUI()
{
    auto* mainLayout = new QHBoxLayout(this);
    mainLayout->setContentsMargins(0, 2, 8, 2);
    mainLayout->setSpacing(4);

    // ── Helpers ───────────────────────────────────────────────────────────
    auto makeSep = [this, mainLayout]() {
        auto* sep = new QFrame(this);
        sep->setFrameShape(QFrame::VLine);
        sep->setFrameShadow(QFrame::Sunken);
        sep->setFixedWidth(1);
        m_separators.append(sep);
        mainLayout->addSpacing(4);
        mainLayout->addWidget(sep);
        mainLayout->addSpacing(4);
    };

    // ── Segmented New | Open | Save button group ──────────────────────────
    m_newBtn  = new QToolButton(this);
    m_openBtn = new QToolButton(this);
    m_saveBtn = new QToolButton(this);

    m_newBtn->setText("New");
    m_openBtn->setText("Open");
    m_saveBtn->setText("Save");

    m_newBtn->setObjectName("TransportNew");
    m_openBtn->setObjectName("TransportOpen");
    m_saveBtn->setObjectName("TransportSave");

    for (auto* btn : {m_newBtn, m_openBtn, m_saveBtn}) {
        btn->setFocusPolicy(Qt::NoFocus);
        btn->setAutoRaise(true);          // flat/transparent in normal state
        btn->setToolButtonStyle(Qt::ToolButtonTextOnly);
    }

    m_newBtn->setToolTip("New Project");
    m_openBtn->setToolTip("Open Project");
    m_saveBtn->setToolTip("Save Project");

    // Sub-widget to hold the three buttons with zero spacing (joined look)
    auto* btnGroup  = new QWidget(this);
    btnGroup->setAttribute(Qt::WA_StyledBackground, false);
    btnGroup->setAutoFillBackground(false);
    auto* btnLayout = new QHBoxLayout(btnGroup);
    btnLayout->setContentsMargins(0, 0, 0, 0);
    btnLayout->setSpacing(0);
    btnLayout->addWidget(m_newBtn);
    btnLayout->addWidget(m_openBtn);
    btnLayout->addWidget(m_saveBtn);
    mainLayout->addWidget(btnGroup);

    makeSep();
    mainLayout->addStretch(1);   // pushes right-side content to the right

    // ── Wavy Labs animated logo — floats as overlay, centred via resizeEvent
    m_wavyLogo = new WavyLogoLabel(this);
    // NOT added to layout — positioned absolutely in resizeEvent

    // ── Build all right-side widgets first, then add in desired order ────
    // Order: VOL | PCH | Clock(POS) | Tempo(BPM) | Seq(TimeSig) | CPU

    // -- Volume knob (inside frame to match LCD widgets) --
    m_volFrame = new QFrame(this);
    m_volFrame->setObjectName("TransportVolFrame");
    m_volFrame->setFixedSize(68, 36);
    m_volFrame->setToolTip("Master Volume (0\xe2\x80\x93""200%)");

    auto* volInner = new QVBoxLayout(m_volFrame);
    volInner->setContentsMargins(6, 1, 6, 1);
    volInner->setSpacing(0);

    auto* volTop = new QWidget(m_volFrame);
    auto* volTopLayout = new QHBoxLayout(volTop);
    volTopLayout->setContentsMargins(0, 0, 0, 0);
    volTopLayout->setSpacing(2);

    m_volumeKnob = new MiniKnob(
        0, 200, m_engine->masterVolume(),
        "Master Volume (0\xe2\x80\x93""200%)",
        [this](int vol) {
            m_engine->setMasterVolume(vol);
            m_volumeLabel->setText(QString::number(vol) + "%");
        }, m_volFrame);

    m_volumeLabel = new QLabel(
        QString::number(m_engine->masterVolume()) + "%", m_volFrame);
    m_volumeLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);

    volTopLayout->addWidget(m_volumeKnob);
    volTopLayout->addWidget(m_volumeLabel);

    m_volIconLabel = new QLabel("VOL", m_volFrame);
    m_volIconLabel->setAlignment(Qt::AlignHCenter | Qt::AlignTop);

    volInner->addWidget(volTop);
    volInner->addWidget(m_volIconLabel);

    // -- Pitch knob (inside frame to match LCD widgets) --
    m_pitchFrame = new QFrame(this);
    m_pitchFrame->setObjectName("TransportPitchFrame");
    m_pitchFrame->setFixedSize(60, 36);
    m_pitchFrame->setToolTip("Master Pitch (\xc2\xb1""12 semitones)");

    auto* pitchInner = new QVBoxLayout(m_pitchFrame);
    pitchInner->setContentsMargins(6, 1, 6, 1);
    pitchInner->setSpacing(0);

    auto* pitchTop = new QWidget(m_pitchFrame);
    auto* pitchTopLayout = new QHBoxLayout(pitchTop);
    pitchTopLayout->setContentsMargins(0, 0, 0, 0);
    pitchTopLayout->setSpacing(2);

    const int initPitch = m_engine->masterPitch();
    m_pitchKnob = new MiniKnob(
        0, 24, initPitch + 12,
        "Master Pitch (\xc2\xb1""12 semitones)",
        [this](int v) {
            const int semitones = v - 12;
            m_engine->setMasterPitch(semitones);
            m_pitchLabel->setText((semitones >= 0 ? "+" : "") + QString::number(semitones));
        }, m_pitchFrame);

    m_pitchLabel = new QLabel(
        (initPitch >= 0 ? "+" : "") + QString::number(initPitch), m_pitchFrame);
    m_pitchLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);

    pitchTopLayout->addWidget(m_pitchKnob);
    pitchTopLayout->addWidget(m_pitchLabel);

    m_pitchIconLabel = new QLabel("PCH", m_pitchFrame);
    m_pitchIconLabel->setAlignment(Qt::AlignHCenter | Qt::AlignTop);

    pitchInner->addWidget(pitchTop);
    pitchInner->addWidget(m_pitchIconLabel);

    // -- Playback position (Clock) --
    m_posFrame = new QFrame(this);
    m_posFrame->setObjectName("TransportPosFrame");
    m_posFrame->setFixedSize(92, 36);
    m_posFrame->setToolTip("Playback position (min:sec:msec)");

    auto* posInner = new QVBoxLayout(m_posFrame);
    posInner->setContentsMargins(4, 1, 4, 1);
    posInner->setSpacing(0);

    m_posLabel = new QLabel("00:00:000", m_posFrame);
    m_posLabel->setAlignment(Qt::AlignHCenter | Qt::AlignBottom);

    m_posSubLabel = new QLabel("MIN  SEC  MSEC", m_posFrame);
    m_posSubLabel->setAlignment(Qt::AlignHCenter | Qt::AlignTop);

    posInner->addWidget(m_posLabel);
    posInner->addWidget(m_posSubLabel);

    // -- BPM / Tempo --
    m_bpmFrame = new QFrame(this);
    m_bpmFrame->setObjectName("TransportLcdFrame");
    m_bpmFrame->setFixedSize(68, 36);
    m_bpmFrame->setToolTip("Tempo — double-click to edit");

    auto* bpmInner = new QVBoxLayout(m_bpmFrame);
    bpmInner->setContentsMargins(4, 1, 4, 1);
    bpmInner->setSpacing(0);

    m_bpmValueLabel = new QLabel(QString::number(m_engine->tempo()), m_bpmFrame);
    m_bpmValueLabel->setObjectName("TransportBpmLcd");
    m_bpmValueLabel->setAlignment(Qt::AlignHCenter | Qt::AlignBottom);

    m_bpmSubLabel = new QLabel("TEMPO/BPM", m_bpmFrame);
    m_bpmSubLabel->setAlignment(Qt::AlignHCenter | Qt::AlignTop);

    bpmInner->addWidget(m_bpmValueLabel);
    bpmInner->addWidget(m_bpmSubLabel);

    m_bpmSpin = new QSpinBox(this);
    m_bpmSpin->setObjectName("TransportBpmSpin");
    m_bpmSpin->setRange(10, 999);
    m_bpmSpin->setValue(m_engine->tempo());
    m_bpmSpin->setFixedSize(68, 36);
    m_bpmSpin->setFocusPolicy(Qt::ClickFocus);
    m_bpmSpin->hide();

    connect(m_bpmSpin, &QSpinBox::valueChanged,    this, &TransportBar::onBpmChanged);
    connect(m_bpmSpin, &QSpinBox::editingFinished, this, [this]() {
        m_bpmValueLabel->setText(QString::number(m_bpmSpin->value()));
        m_bpmFrame->show();
        m_bpmSpin->hide();
    });
    m_bpmFrame->installEventFilter(this);

    // -- Time Signature (Seq) --
    m_timeSigLabel = new QLabel(
        QString("%1\n%2")
            .arg(m_engine->timeSigNumerator())
            .arg(m_engine->timeSigDenominator()),
        this);
    m_timeSigLabel->setObjectName("TransportTimeSig");
    m_timeSigLabel->setAlignment(Qt::AlignCenter);
    m_timeSigLabel->setFixedSize(28, 36);
    m_timeSigLabel->setToolTip("Time Signature");
    // colour applied by applyThemeColors()

    // -- CPU meter --
    m_cpuFrame = new QFrame(this);
    m_cpuFrame->setFixedSize(64, 36);
    m_cpuFrame->setToolTip("Audio engine CPU usage");

    auto* cpuInner = new QVBoxLayout(m_cpuFrame);
    cpuInner->setContentsMargins(4, 1, 4, 1);
    cpuInner->setSpacing(0);

    m_cpuLabel = new QLabel("0%", m_cpuFrame);
    m_cpuLabel->setAlignment(Qt::AlignHCenter | Qt::AlignBottom);

    m_cpuSubLabel = new QLabel("CPU", m_cpuFrame);
    m_cpuSubLabel->setAlignment(Qt::AlignHCenter | Qt::AlignTop);

    cpuInner->addWidget(m_cpuLabel);
    cpuInner->addWidget(m_cpuSubLabel);

    // ── Genre Mode selector with gear overlay ──────────────────────────────
    // The combo gets full LCD-frame styling (same as BPM/Clock/CPU).
    // The gear button is a child of the combo, overlaid on its right edge,
    // replacing the normal drop-down arrow area.
    m_genreCombo = new QComboBox(this);
    m_genreCombo->setFixedHeight(36);
    m_genreCombo->setMinimumWidth(140);
    m_genreCombo->setMaximumWidth(170);
    for (int i = 0; i < kGenreModeCount; ++i)
        m_genreCombo->addItem(QString(kGenreModes[i].displayName).toUpper(),
                              QString(kGenreModes[i].key));
    m_genreCombo->addItem(QStringLiteral("CUSTOM"), QStringLiteral("custom"));
    connect(m_genreCombo, QOverload<int>::of(&QComboBox::activated),
            this, [this](int) {
                emit genreModeRequested(m_genreCombo->currentData().toString());
            });

    // Gear button — overlaid as child of the combo, right edge
    m_genreSettingsBtn = new QToolButton(m_genreCombo);
    m_genreSettingsBtn->setText(QString::fromUtf8("\xe2\x9a\x99")); // ⚙
    m_genreSettingsBtn->setFixedSize(22, 34);
    m_genreSettingsBtn->setCursor(Qt::PointingHandCursor);
    m_genreSettingsBtn->setToolTip("Genre Settings");
    m_genreSettingsBtn->setFocusPolicy(Qt::NoFocus);
    // Position it on the right edge of the combo (updated in resizeEvent too)
    connect(m_genreSettingsBtn, &QToolButton::clicked, this, [this]() {
        if (!m_genrePopup || !m_genreCombo) return;
        const QString key = m_genreCombo->currentData().toString();
        m_genrePopup->loadGenre(key);
        m_genrePopup->showBelow(m_genreCombo);
    });

    m_genreCombo->installEventFilter(this);  // position gear on resize

    // ── Add to layout: Genre | VOL | PCH | Clock | Tempo | Seq | CPU
    mainLayout->addWidget(m_genreCombo);
    mainLayout->addSpacing(4);

    mainLayout->addWidget(m_volFrame);
    mainLayout->addSpacing(4);

    mainLayout->addWidget(m_pitchFrame);
    mainLayout->addSpacing(4);

    mainLayout->addWidget(m_posFrame);
    mainLayout->addSpacing(4);

    mainLayout->addWidget(m_bpmFrame);
    mainLayout->addWidget(m_bpmSpin);
    mainLayout->addSpacing(4);

    mainLayout->addWidget(m_timeSigLabel);
    mainLayout->addSpacing(8);

    mainLayout->addWidget(m_cpuFrame);

    applyThemeColors();
}

// ---------------------------------------------------------------------------
// Event filter — double-click on BPM LCD frame reveals the spinbox
// ---------------------------------------------------------------------------

bool TransportBar::eventFilter(QObject* obj, QEvent* event)
{
    if (obj == m_bpmFrame && event->type() == QEvent::MouseButtonDblClick) {
        m_bpmFrame->hide();
        m_bpmSpin->show();
        m_bpmSpin->setFocus();
        m_bpmSpin->selectAll();
        return true;
    }
    // Keep gear button pinned to combo's right edge
    if (obj == m_genreCombo && event->type() == QEvent::Resize && m_genreSettingsBtn) {
        const int x = m_genreCombo->width() - m_genreSettingsBtn->width() - 1;
        m_genreSettingsBtn->move(x, 1);
    }
    return QWidget::eventFilter(obj, event);
}

// ---------------------------------------------------------------------------

#ifdef WAVY_LMMS_CORE
void TransportBar::setMainWindow(lmms::gui::MainWindow* win)
{
    if (!win) return;
    connect(m_newBtn,  &QToolButton::clicked, this, [win]() {
        QMetaObject::invokeMethod(win, "createNewProject", Qt::QueuedConnection);
    });
    connect(m_openBtn, &QToolButton::clicked, this, [win]() {
        QMetaObject::invokeMethod(win, "openProject", Qt::QueuedConnection);
    });
    connect(m_saveBtn, &QToolButton::clicked, this, [win]() {
        QMetaObject::invokeMethod(win, "saveProject", Qt::QueuedConnection);
    });
}
#endif

// ---------------------------------------------------------------------------

void TransportBar::onBpmChanged(int bpm)
{
    m_engine->setTempo(bpm);
    m_bpmValueLabel->setText(QString::number(bpm));
}

void TransportBar::resizeEvent(QResizeEvent* e)
{
    QWidget::resizeEvent(e);
    if (m_wavyLogo) {
        // Centre relative to the full WavyHeader (our parent spans the whole
        // window width), not just the transport bar which starts after the menu.
        const int parentW  = parentWidget() ? parentWidget()->width() : width();
        const int myLeft   = pos().x();   // our left edge inside the parent
        const int x = parentW / 2 - myLeft - m_wavyLogo->width() / 2;
        const int y = (height() - m_wavyLogo->height()) / 2;
        m_wavyLogo->move(qMax(0, x), y);
        m_wavyLogo->raise();
    }
}

// ---------------------------------------------------------------------------
// applyThemeColors — called at startup and on every theme change
// ---------------------------------------------------------------------------

void TransportBar::applyThemeColors()
{
    auto* th = Wavy::ThemeManager::themeObject();
    if (!th) return;

    const QColor accent  = th->accent();
    const QColor outline = th->outline();

    // LCD background: near-black, lightly tinted by the accent hue
    const QColor lcdBg = QColor(
        qMin(255, accent.red()   / 12 + 4),
        qMin(255, accent.green() / 12 + 4),
        qMin(255, accent.blue()  / 12 + 7));

    // LCD border / sub-label: 35% of accent (dark, desaturated)
    const QColor lcdBorder = QColor(
        qMin(255, int(accent.red()   * 0.35)),
        qMin(255, int(accent.green() * 0.35)),
        qMin(255, int(accent.blue()  * 0.35)));

    const QString bgStr     = lcdBg.name();
    const QString borderStr = lcdBorder.name();
    const QString accentStr = accent.name();

    // Frames — all LCD-style widgets share the same dark bg
    const QString frameQss =
        QString("background: %1; border: 1px solid %2; border-radius: 3px;")
        .arg(bgStr, borderStr);
    m_posFrame->setStyleSheet(QString("#TransportPosFrame {%1}").arg(frameQss));
    m_bpmFrame->setStyleSheet(QString("#TransportLcdFrame {%1}").arg(frameQss));
    m_cpuFrame->setStyleSheet(QString("QFrame {%1}").arg(frameQss));
    m_volFrame->setStyleSheet(QString("#TransportVolFrame {%1}").arg(frameQss));
    m_pitchFrame->setStyleSheet(QString("#TransportPitchFrame {%1}").arg(frameQss));

    // Time signature widget (combined frame + digit)
    m_timeSigLabel->setStyleSheet(
        QString("color: %1; font-family: 'Courier New', monospace;"
                " font-size: 12px; font-weight: bold;"
                " background: %2; border: 1px solid %3; border-radius: 3px;")
        .arg(accentStr, bgStr, borderStr));

    // Digit / value labels (full accent)
    const QString digitBase =
        QString("color: %1; font-family: 'Courier New', monospace;"
                " background: transparent;").arg(accentStr);
    m_posLabel->setStyleSheet(digitBase + " font-size: 13px; font-weight: bold;");
    m_bpmValueLabel->setStyleSheet(digitBase + " font-size: 17px; font-weight: bold;");
    m_cpuLabel->setStyleSheet(digitBase + " font-size: 13px; font-weight: bold;");

    // VOL / PCH value labels — accent, inside dark frame
    m_volumeLabel->setStyleSheet(digitBase + " font-size: 13px; font-weight: bold;");
    m_pitchLabel->setStyleSheet(digitBase + " font-size: 13px; font-weight: bold;");

    // Sub-labels inside LCD frames — 75% accent for readability on dark LCD bg
    const QColor lcdSub = QColor(
        qMin(255, int(accent.red()   * 0.75)),
        qMin(255, int(accent.green() * 0.75)),
        qMin(255, int(accent.blue()  * 0.75)));
    const QString lcdSubQss =
        QString("color: %1; font-size: 8px; background: transparent;").arg(lcdSub.name());
    m_posSubLabel->setStyleSheet(lcdSubQss);
    m_bpmSubLabel->setStyleSheet(lcdSubQss);
    m_cpuSubLabel->setStyleSheet(lcdSubQss);

    // VOL / PCH sub-labels — same style as other sub-labels
    m_volIconLabel->setStyleSheet(lcdSubQss);
    m_pitchIconLabel->setStyleSheet(lcdSubQss);

    // Separator lines
    const QString sepStr = outline.name();
    for (auto* sep : m_separators)
        sep->setStyleSheet(QString("color: %1;").arg(sepStr));

    // Genre combo — full LCD frame, with extra right padding for gear overlay
    if (m_genreCombo) {
        m_genreCombo->setStyleSheet(QString(R"(
            QComboBox {
                background: %1;
                color: %2;
                border: 1px solid %3;
                border-radius: 3px;
                padding: 2px 26px 2px 8px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                font-weight: bold;
            }
            QComboBox:hover {
                border: 1px solid %2;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 24px;
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0; height: 0;
            }
            QComboBox QAbstractItemView {
                background: %1;
                color: %2;
                border: 1px solid %3;
                selection-background-color: %3;
                selection-color: %2;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 3px 8px;
            }
        )").arg(bgStr, accentStr, borderStr));
    }

    // Gear button — transparent overlay inside the combo
    if (m_genreSettingsBtn) {
        m_genreSettingsBtn->setStyleSheet(QString(R"(
            QToolButton {
                background: transparent;
                color: %1;
                border: none;
                border-left: 1px solid %2;
                border-radius: 0px;
                font-size: 12px;
                padding: 0px;
            }
            QToolButton:hover {
                color: %3;
            }
        )").arg(borderStr, borderStr, accentStr));
    }

    // Repaint knobs (they read ThemeManager directly in paintEvent)
    if (m_volumeKnob) m_volumeKnob->update();
    if (m_pitchKnob)  m_pitchKnob->update();
}

// ---------------------------------------------------------------------------

void TransportBar::setGenreMode(const QString& displayName)
{
    if (!m_genreCombo) return;
    QSignalBlocker b(m_genreCombo);   // don't re-emit activated
    const int idx = m_genreCombo->findText(displayName.toUpper());
    if (idx >= 0) m_genreCombo->setCurrentIndex(idx);
}

void TransportBar::setBackend(AIBackend* backend)
{
    if (!backend || m_backend) return;
    m_backend = backend;

    m_genrePopup = new GenreConfigPopup(backend, this);

    // Apply from popup → re-use existing genre mode wiring
    connect(m_genrePopup, &GenreConfigPopup::applyRequested,
            this, &TransportBar::genreModeRequested);
}

// ---------------------------------------------------------------------------

void TransportBar::updatePosition()
{
    // ── Playback position ─────────────────────────────────────────────────
    const int ticks = m_engine->playPositionTicks();
    if (ticks <= 0) {
        m_posLabel->setText("00:00:000");
    } else {
        constexpr int TICKS_PER_BEAT = 48;   // = DEFAULT_TICKS_PER_TACT / 4
        const double bpm     = m_engine->tempo();
        const double seconds = (static_cast<double>(ticks) / TICKS_PER_BEAT) * (60.0 / bpm);
        const int totalMs  = static_cast<int>(seconds * 1000.0);
        const int ms       = totalMs % 1000;
        const int totalSec = totalMs / 1000;
        const int sec      = totalSec % 60;
        const int min      = totalSec / 60;
        m_posLabel->setText(QString("%1:%2:%3")
            .arg(min, 2, 10, QChar('0'))
            .arg(sec, 2, 10, QChar('0'))
            .arg(ms,  3, 10, QChar('0')));
    }

    // ── Time signature (poll for changes) ────────────────────────────────
    const int num = m_engine->timeSigNumerator();
    const int den = m_engine->timeSigDenominator();
    if (num != m_lastTimeSigNum || den != m_lastTimeSigDen) {
        m_lastTimeSigNum = num;
        m_lastTimeSigDen = den;
        m_timeSigLabel->setText(QString("%1\n%2").arg(num).arg(den));
    }

    // ── CPU meter ─────────────────────────────────────────────────────────
    m_cpuLabel->setText(QString::number(m_engine->cpuLoad()) + "%");
}
