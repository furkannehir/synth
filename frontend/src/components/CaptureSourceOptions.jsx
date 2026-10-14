export default function CaptureSourceOptions({ sources }) {
  const screens = sources.filter((source) => source.kind === "screen");
  const windows = sources.filter((source) => source.kind !== "screen");
  return <>
    <option value="">Choose a source</option>
    {screens.length > 0 && <optgroup label="Entire screens">{screens.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}</optgroup>}
    {windows.length > 0 && <optgroup label="Windows">{windows.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}</optgroup>}
  </>;
}
