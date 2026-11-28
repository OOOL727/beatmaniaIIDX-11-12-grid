(() => {
  "use strict";

  const lamps = ["NO PLAY", "FAILED", "ASSIST CLEAR", "EASY CLEAR", "CLEAR", "HARD CLEAR", "EX HARD CLEAR", "FULLCOMBO CLEAR"];
  const charts = ["H", "A", "L"];
  const columns = ["HYPER", "ANOTHER", "LEGGENDARIA"];
  // ☆11適正の架空プロフィール。各レベルの易しい帯・難しい帯のランプ比率。
  const profiles = {
    9: [[4, 1, 1, 2, 6, 35, 35, 16], [12, 6, 4, 7, 20, 33, 16, 2]],
    10: [[7, 3, 3, 6, 17, 43, 18, 3], [22, 12, 10, 14, 23, 16, 3, 0]],
    11: [[15, 10, 9, 12, 22, 27, 5, 0], [60, 32, 5, 2, 1, 0, 0, 0]],
    12: [[55, 29, 8, 5, 2, 1, 0, 0], [88, 11, 1, 0, 0, 0, 0, 0]]
  };
  const bpRanges = [[0, 0], [45, 100], [40, 90], [25, 75], [15, 60], [4, 32], [1, 10], [0, 0]];

  function roll(key, salt) {
    let hash = 2166136261;
    for (const char of salt + "|" + key) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
    return (hash >>> 0) / 4294967296;
  }

  function createCsv(groups, keyOf, bandsFor = window.skillBandsFor) {
    const header = ["タイトル", ...columns.flatMap(name => [name + " 難易度", name + " クリアタイプ", name + " ミスカウント"])];
    const rows = [header];
    const seen = new Set();
    const referenceTiers = new Map();
    // ☆10の共通譜面はRatingと同じ胡椒氏版NORMAL帯を基準にする。
    groups.forEach(({level, table}) => {
      const bands = bandsFor(level);
      table.forEach(row => {
        if (bands.includes(row[0])) referenceTiers.set(level + "|" + keyOf(row[2]).join("|"), row[0]);
      });
    });
    groups.forEach(({level, table}) => {
      const bands = bandsFor(level);
      table.forEach(row => {
        const [title, chart] = keyOf(row[2]);
        const key = title + "|" + chart;
        if (seen.has(key)) return;
        seen.add(key);
        const seed = level + "|" + key;
        const tier = referenceTiers.get(seed) ?? row[0];
        const index = bands.indexOf(tier);
        const numericTier = /^難度(\d+)/.exec(tier);
        const difficulty = index >= 0 ? index / Math.max(1, bands.length - 1)
          : numericTier ? Math.min(1, Number(numericTier[1]) / 10) : 0.5;
        const [easy, hard] = profiles[level];
        const weights = easy.map((weight, i) => weight + (hard[i] - weight) * difficulty);
        let rank = 0, remaining = roll(seed, "lamp") * 100;
        while (rank < weights.length - 1 && remaining >= weights[rank]) remaining -= weights[rank++];
        const [low, high] = bpRanges[rank];
        const bp = rank === 0 ? "" : String(Math.round(
          (low + (high - low) * roll(seed, "bp")) * (1 + (level - 9) * 0.45 + difficulty * 0.35)
        ));
        const slot = charts.indexOf(chart);
        const record = [row[2].replace(/\((H|L)\)\s*$/, "").trim(), ...Array(9).fill("")];
        record[1 + slot * 3] = String(level);
        record[2 + slot * 3] = lamps[rank];
        record[3 + slot * 3] = bp;
        rows.push(record);
      });
    });
    return rows.map(row => row.map(value => '"' + String(value).replace(/"/g, '""') + '"').join(",")).join("\n");
  }

  window.LampGridDemo = Object.freeze({createCsv});
})();
