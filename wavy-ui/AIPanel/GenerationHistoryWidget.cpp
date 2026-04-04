#include "GenerationHistoryWidget.h"
#include <QListWidgetItem>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QFrame>
#include <QDrag>
#include <QMimeData>
#include <QPainter>
#include <QPainterPath>
#include <QRandomGenerator>
#include <QDesktopServices>
#include <QFileInfo>
#include <QUrl>

// Simple placeholder waveform: vertical bars with varied heights (no audio decode).
class WaveformBars : public QWidget
{
public:
    explicit WaveformBars(int barCount = 32, QWidget* parent = nullptr)
        : QWidget(parent), m_barCount(barCount)
    {
        setFixedHeight(28);
        setMinimumWidth(80);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        setAttribute(Qt::WA_OpaquePaintEvent, false);
        // Deterministic-ish pattern from bar count
        m_heights.resize(m_barCount);
        for (int i = 0; i < m_barCount; ++i)
            m_heights[i] = 0.25f + 0.65f * (0.5f + 0.5f * std::sin(i * 0.7f)) * (0.7f + 0.3f * (i % 5) / 5.f);
    }

protected:
    void paintEvent(QPaintEvent*) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing, false);
        const int w = width();
        const int h = height();
        const int barW = qMax(2, (w - (m_barCount - 1)) / m_barCount);
        const int gap = w > m_barCount * (barW + 1) ? 1 : 0;
        const int totalBarW = barW + gap;
        const int midY = h / 2;
        p.fillRect(rect(), Qt::transparent);
        for (int i = 0; i < m_barCount && i * totalBarW < w; ++i) {
            const int barH = qMax(2, static_cast<int>(m_heights[i] * (h / 2)));
            const int x = i * totalBarW;
            const QRect barRect(x, midY - barH / 2, barW, barH);
            p.fillRect(barRect, QColor(220, 224, 238, 140));
        }
    }

private:
    int m_barCount;
    QVector<float> m_heights;
};

// List widget that starts a drag with LMMS "samplefile" mime data so drops on the DAW create a track.
class GenerationsListWidget : public QListWidget
{
public:
    explicit GenerationsListWidget(QWidget* parent = nullptr) : QListWidget(parent)
    {
        setDragEnabled(true);
        setDragDropMode(QAbstractItemView::DragOnly);
    }

protected:
    void startDrag(Qt::DropActions supportedActions) override
    {
        Q_UNUSED(supportedActions);
        QModelIndexList indexes = selectedIndexes();
        if (indexes.isEmpty()) return;
        QListWidgetItem* item = itemFromIndex(indexes.first());
        if (!item) return;
        QString path = item->data(Qt::UserRole).toString();
        if (path.isEmpty()) return;
        QMimeData* mime = new QMimeData();
        mime->setData(QStringLiteral("application/x-lmms-stringpair"),
                      (QStringLiteral("samplefile:") + path).toUtf8());
        QDrag* drag = new QDrag(this);
        drag->setMimeData(mime);
        drag->exec(Qt::CopyAction, Qt::CopyAction);
    }
};

GenerationHistoryWidget::GenerationHistoryWidget(QWidget* parent)
    : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 4, 0, 0);
    layout->setSpacing(4);

    auto* header = new QLabel("Generations", this);
    header->setObjectName("sectionHeader");
    layout->addWidget(header);

    m_list = new GenerationsListWidget(this);
    m_list->setObjectName("historyList");
    m_list->setSpacing(4);
    connect(m_list, &QListWidget::itemDoubleClicked,
            this, &GenerationHistoryWidget::onItemDoubleClicked);
    layout->addWidget(m_list);
}

void GenerationHistoryWidget::addEntry(const QString& prompt,
                                        const QString& audioPath,
                                        double duration,
                                        const QVariantList& sections)
{
    const int variationIndex = m_list->count() + 1;
    auto* item = new QListWidgetItem(m_list);
    item->setData(Qt::UserRole, audioPath);
    item->setData(Qt::UserRole + 1, sections);

    // One compound widget: label above + card
    auto* wrapper = new QWidget(m_list);
    wrapper->setObjectName("generationEntryWrapper");
    auto* vLayout = new QVBoxLayout(wrapper);
    vLayout->setContentsMargins(0, 2, 0, 4);
    vLayout->setSpacing(4);

    // Label above card (e.g. prompt snippet)
    const QString labelText = prompt.isEmpty() ? QString("Generation") : prompt.left(24).trimmed();
    auto* label = new QLabel(labelText, wrapper);
    label->setObjectName("generationCardLabel");
    vLayout->addWidget(label);

    // Card: dark rounded container (styled in wavy-dark style.qss)
    auto* card = new QFrame(wrapper);
    card->setObjectName("generationCard");
    auto* hl = new QHBoxLayout(card);
    hl->setContentsMargins(10, 8, 10, 8);
    hl->setSpacing(12);

    // Title: "Variation N"
    auto* titleLabel = new QLabel(QString("Variation %1").arg(variationIndex), card);
    titleLabel->setObjectName("generationCardTitle");
    hl->addWidget(titleLabel);

    // Play button
    auto* playBtn = new QPushButton(card);
    playBtn->setObjectName("generationPlayBtn");
    playBtn->setFixedSize(28, 28);
    playBtn->setCursor(Qt::PointingHandCursor);
    playBtn->setText("\u25B6"); // ▶
    playBtn->setToolTip("Play");
    connect(playBtn, &QPushButton::clicked, this, [this, audioPath]() {
        emit entryPlayRequested(audioPath);
    });
    hl->addWidget(playBtn);

    // Waveform placeholder
    const int barCount = qBound(20, static_cast<int>(duration * 1.5), 48);
    auto* waveform = new WaveformBars(barCount, card);
    hl->addWidget(waveform, 1);

    // Star (favorite) – icon only
    auto* starBtn = new QPushButton("\u2606", card); // ☆
    starBtn->setObjectName("generationStarBtn");
    starBtn->setFixedSize(28, 28);
    starBtn->setCursor(Qt::PointingHandCursor);
    starBtn->setToolTip("Favorite");
    hl->addWidget(starBtn);

    // Download – open file location
    auto* downloadBtn = new QPushButton("\u2193", card); // ↓
    downloadBtn->setObjectName("generationDownloadBtn");
    downloadBtn->setFixedSize(28, 28);
    downloadBtn->setCursor(Qt::PointingHandCursor);
    downloadBtn->setToolTip("Open file location");
    connect(downloadBtn, &QPushButton::clicked, this, [audioPath]() {
        const QFileInfo fi(audioPath);
        if (fi.exists())
            QDesktopServices::openUrl(QUrl::fromLocalFile(fi.absolutePath()));
    });
    hl->addWidget(downloadBtn);

    // Insert into DAW – icon only to match star/download
    auto* insertBtn = new QPushButton("\u002B", card); // +
    insertBtn->setObjectName("generationInsertBtn");
    insertBtn->setFixedSize(28, 28);
    insertBtn->setCursor(Qt::PointingHandCursor);
    insertBtn->setToolTip("Insert into project");
    connect(insertBtn, &QPushButton::clicked, this, [this, audioPath, prompt, sections]() {
        emit entryInsertRequested(audioPath, prompt.left(30), sections);
    });
    hl->addWidget(insertBtn);

    card->setMinimumHeight(48);
    vLayout->addWidget(card);
    wrapper->setMinimumHeight(70);
    item->setSizeHint(wrapper->sizeHint());
    m_list->setItemWidget(item, wrapper);
    m_list->scrollToBottom();
}

void GenerationHistoryWidget::clear()
{
    m_list->clear();
}

void GenerationHistoryWidget::onItemDoubleClicked(QListWidgetItem* item)
{
    if (item)
        emit entryPlayRequested(item->data(Qt::UserRole).toString());
}
