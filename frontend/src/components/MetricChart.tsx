import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { CurvePoint } from '../types';

interface MetricChartProps {
  data: CurvePoint[];
  title: string;
  emptyLabel: string;
  series: {
    key: keyof CurvePoint;
    name: string;
    color: string;
    strokeDasharray?: string;
  }[];
}

export const MetricChart: React.FC<MetricChartProps> = ({
  data,
  title,
  emptyLabel,
  series,
}) => {
  if (!data || data.length === 0) {
    return (
      <div className="bg-slate-950/80 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between min-h-[140px]">
        <div className="text-xs font-semibold text-slate-300">{title}</div>
        <div className="text-xs text-slate-500 font-mono text-center my-auto py-6">
          {emptyLabel}
        </div>
      </div>
    );
  }

  const latestPoint = data[data.length - 1];

  return (
    <div className="bg-slate-950/80 border border-slate-800/80 rounded-xl p-3 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-200">{title}</span>
        <div className="flex flex-wrap items-center gap-3">
          {series.map(s => {
            const val = latestPoint ? latestPoint[s.key] : null;
            return (
              <span key={s.name} className="inline-flex items-center gap-1.5 text-[11px] font-mono text-slate-300">
                <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: s.color }} />
                <span className="text-slate-400">{s.name}:</span>
                <strong className="text-white">
                  {typeof val === 'number' ? val.toFixed(4) : '—'}
                </strong>
              </span>
            );
          })}
        </div>
      </div>

      <div className="h-28 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis
              dataKey="step"
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              tickFormatter={(step) => `${step}`}
            />
            <YAxis
              stroke="#64748b"
              fontSize={10}
              domain={['auto', 'auto']}
              tickLine={false}
              tickFormatter={(val) => Number(val).toFixed(2)}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#090d16',
                border: '1px solid #1e293b',
                borderRadius: '0.5rem',
                fontSize: '11px',
                fontFamily: 'JetBrains Mono',
              }}
              labelStyle={{ color: '#94a3b8' }}
              labelFormatter={(step) => `Step: ${step}`}
              formatter={(value: any, name: any) => [
                typeof value === 'number' ? value.toFixed(5) : value,
                name,
              ]}
            />
            {series.map(s => (
              <Line
                key={String(s.key)}
                type="monotone"
                dataKey={s.key}
                name={s.name}
                stroke={s.color}
                strokeWidth={1.75}
                strokeDasharray={s.strokeDasharray}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

