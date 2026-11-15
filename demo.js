(() => {
  "use strict";

  const lamps = ["HARD CLEAR", "CLEAR", "EASY CLEAR", "EX HARD CLEAR", "ASSIST CLEAR", "FAILED", "FULLCOMBO CLEAR"];
  const charts = ["H", "A", "L"];
  const columns = ["HYPER", "ANOTHER", "LEGGENDARIA"];

  function createCsv(groups, keyOf) {
    const header = ["タイトル", ...columns.flatMap(name => [name + " 難易度", name + " クリアタイプ", name + " ミスカウント"])];
    const rows = [header];
    const seen = new Set();
    groups.forEach(({level, table}) => {
      const step = Math.max(1, Math.floor(table.length / 60));
      table.forEach((row, index) => {
        if (index % step !== 0) return;
        const [title, chart] = keyOf(row[2]);
        const key = title + "|" + chart;
        if (seen.has(key)) return;
        seen.add(key);
        const slot = charts.indexOf(chart);
        const record = [title, ...Array(9).fill("")];
        record[1 + slot * 3] = String(level);
        record[2 + slot * 3] = lamps[rows.length % lamps.length];
        record[3 + slot * 3] = String(5 + (rows.length * 7) % 70);
        rows.push(record);
      });
    });
    return rows.map(row => row.map(value => '"' + String(value).replace(/"/g, '""') + '"').join(",")).join("\n");
  }

  window.LampGridDemo = Object.freeze({createCsv});
})();
