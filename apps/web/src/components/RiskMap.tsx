import { useEffect } from 'react';
import { circleMarker, geoJSON } from 'leaflet';
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';
import type { RiskMapData } from '../api/types';
import { percent, riskRange } from '../lib/format';
import { RiskChip } from './ui';
import { riskColors } from '../lib/risk';

type Feature = RiskMapData['features'][number];

function FitBounds({ features }: { features: Feature[] }) {
  const map = useMap();
  useEffect(() => {
    if (features.length)
      map.fitBounds(geoJSON(features).getBounds(), {
        padding: [25, 25],
        maxZoom: 10,
        animate: false,
      });
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [features, map]);
  return null;
}

export function RiskMap({ data, select }: { data: RiskMapData; select: (ubigeo: string) => void }) {
  return (
    <>
      <div className="map-frame">
        <MapContainer
          center={[-5.1, -80.2]}
          zoom={7}
          scrollWheelZoom={false}
          zoomAnimation={false}
          fadeAnimation={false}
          markerZoomAnimation={false}
          className="risk-map"
          aria-label="Mapa de riesgo por distrito de Piura"
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          />
          <FitBounds features={data.features} />
          <GeoJSON
            key={JSON.stringify(data.features)}
            data={data}
            style={(feature) => ({
              color: '#ffffff',
              weight: 1.5,
              fillColor:
                riskColors[
                  (feature?.properties.nivel_riesgo as keyof typeof riskColors) || 'missing'
                ],
              fillOpacity: 0.8,
            })}
            pointToLayer={(feature, latlng) =>
              circleMarker(latlng, {
                radius: 7,
                color: '#ffffff',
                weight: 1.8,
                fillOpacity: 0.95,
                fillColor:
                  riskColors[
                    (feature.properties.nivel_riesgo as keyof typeof riskColors) || 'missing'
                  ],
              })
            }
            onEachFeature={(feature, layer) => {
              const p = feature.properties;
              const tooltip = document.createElement('div');
              const name = document.createElement('strong');
              name.textContent = p.distrito;
              const text = document.createElement('div');
              text.textContent = `${p.nivel_riesgo_etiqueta} · ${percent(p.probabilidad_brote)}`;
              tooltip.append(name, text);
              layer.bindTooltip(tooltip);
              layer.on('click', () => select(p.ubigeo));
            }}
          />
        </MapContainer>
        <span className="map-note">
          {data.features.some((f) => f.geometry.type === 'Point')
            ? 'Centroides distritales · no son límites territoriales'
            : 'Límites distritales'}
        </span>
      </div>
      <div className="map-legend" aria-label="Leyenda de riesgo">
        {data.leyenda.map((l) => (
          <div key={l.nivel || 'missing'}>
            <RiskChip level={l.nivel} label={l.etiqueta} />
            <small>{riskRange(l.desde, l.hasta)}</small>
          </div>
        ))}
      </div>
    </>
  );
}
