import { useOutletContext, useSearchParams } from 'react-router-dom';
import type { AppContext } from '../App';
import { Card, Empty, RiskChip } from '../components/ui';
import content from '../content/help.json';
import { riskRange } from '../lib/format';
import '../help.css';

function normalize(value: string) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es')
    .trim();
}

export function HelpPage() {
  const { configuration } = useOutletContext<AppContext>();
  const [params, setParams] = useSearchParams();
  const query = params.get('ayuda_buscar') || '';
  const words = normalize(query).split(/\s+/).filter(Boolean);
  const topics = content.topics.filter((topic) => {
    const text = normalize(
      [topic.title, topic.summary, ...topic.keywords, ...topic.paragraphs, ...topic.steps].join(
        ' ',
      ),
    );
    return words.every((word) => text.includes(word));
  });
  const selected = topics.find((topic) => topic.id === params.get('ayuda_tema')) || topics[0];
  const selectedIndex = topics.findIndex((topic) => topic.id === selected?.id);

  function search(value: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set('ayuda_buscar', value);
        else next.delete('ayuda_buscar');
        return next;
      },
      { replace: true },
    );
  }

  function select(id: string, clearSearch = false) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set('ayuda_tema', id);
      if (clearSearch) next.delete('ayuda_buscar');
      return next;
    });
  }

  return (
    <div className="help-page">
      <Card className="help-search-card" title={content.title} subtitle={content.intro}>
        <form
          role="search"
          aria-label={content.ui.searchLabel}
          onSubmit={(e) => e.preventDefault()}
        >
          <label htmlFor="help-search">{content.ui.searchLabel}</label>
          <div className="help-search-row">
            <div className="help-search-input">
              <img src="/assets/search.svg" width="18" height="18" alt="" />
              <input
                id="help-search"
                type="search"
                value={query}
                placeholder={content.ui.searchPlaceholder}
                aria-describedby="help-search-hint help-search-count"
                onChange={(e) => search(e.target.value)}
              />
            </div>
            <button type="button" disabled={!query} onClick={() => search('')}>
              {content.ui.clear}
            </button>
          </div>
          <p id="help-search-hint" className="help-muted">
            {content.ui.searchHint}
          </p>
          <p id="help-search-count" role="status" aria-live="polite" aria-atomic="true">
            {content.ui.results}: {topics.length} / {content.topics.length}
          </p>
        </form>
      </Card>

      <div className="help-layout">
        <aside className="help-index-column" aria-label={content.ui.index}>
          <Card title={content.ui.index}>
            <nav aria-label="Temas de ayuda" className="help-topic-index">
              {topics.map((topic) => (
                <button
                  key={topic.id}
                  type="button"
                  aria-current={selected?.id === topic.id ? 'true' : undefined}
                  aria-controls="help-topic-content"
                  onClick={() => select(topic.id)}
                >
                  {topic.title}
                </button>
              ))}
            </nav>
          </Card>
          <Card className="help-manual" title={content.manual.title}>
            <p>{content.manual.description}</p>
            <a className="button primary full-width" href={content.manual.href} download>
              {content.manual.download}
            </a>
          </Card>
        </aside>

        <Card className="help-topic-card">
          <div id="help-topic-content">
            {selected ? (
              <article aria-labelledby={`help-title-${selected.id}`}>
                <p className="eyebrow">{content.ui.topic}</p>
                <h2 id={`help-title-${selected.id}`}>{selected.title}</h2>
                <p className="help-topic-summary">{selected.summary}</p>
                {selected.paragraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
                {selected.steps.length > 0 && (
                  <ol className="help-steps">
                    {selected.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                )}
                {'liveLegend' in selected && selected.liveLegend && (
                  <section className="help-live-legend" aria-labelledby="help-legend-title">
                    <h3 id="help-legend-title">{content.ui.legendTitle}</h3>
                    <p className="help-muted">{content.ui.legendLive}</p>
                    {configuration.leyenda.length ? (
                      <ul>
                        {configuration.leyenda.map((level) => (
                          <li key={level.nivel || 'missing'}>
                            <RiskChip level={level.nivel} label={level.etiqueta} />
                            <span>{riskRange(level.desde, level.hasta)}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>{content.ui.legendEmpty}</p>
                    )}
                  </section>
                )}
                <nav className="help-topic-pagination" aria-label="Recorrido de la guía">
                  <button
                    type="button"
                    disabled={selectedIndex <= 0}
                    onClick={() => select(topics[selectedIndex - 1].id)}
                  >
                    {content.ui.previous}
                  </button>
                  <button
                    type="button"
                    disabled={selectedIndex >= topics.length - 1}
                    onClick={() => select(topics[selectedIndex + 1].id)}
                  >
                    {content.ui.next}
                  </button>
                </nav>
              </article>
            ) : (
              <>
                <Empty title={content.ui.emptyTitle}>{content.ui.emptyText}</Empty>
                <button type="button" className="button primary" onClick={() => search('')}>
                  {content.ui.clear}
                </button>
              </>
            )}
          </div>
        </Card>

        <aside className="help-support-column" aria-label="Recursos de ayuda">
          <Card title={content.troubleshooting.title}>
            <ul className="help-troubleshooting">
              {content.troubleshooting.items.map((item) => (
                <li key={item.topic}>
                  <button
                    type="button"
                    onClick={() => select(item.topic, true)}
                    aria-controls="help-topic-content"
                  >
                    {item.question}
                  </button>
                  <p>{item.answer}</p>
                </li>
              ))}
            </ul>
          </Card>
          <Card title={content.support.title}>
            <p className="help-support-status">{content.support.status}</p>
            {content.support.paragraphs.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </Card>
        </aside>
      </div>
    </div>
  );
}
