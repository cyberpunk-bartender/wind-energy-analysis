# wind-energy-analysis
Show the wind roses of Tokyo, Tohoku and Hokkaido

本プロジェクトは、日本海洋データセンター（JODC）の気象データ（2019-2023年）を用いて、風力発電のポテンシャルと出力変動の平滑化効果を解析したものです。

以下のリンクから、各観測所の風速および風向分布（Wind Rose）をインタラクティブなマップで確認できます。
👉 [【風力発電ポテンシャル・風向分布マップをフルスクリーンで見る】](https://cyberpunk-bartender.github.io/wind-energy-analysis/wind_map_master.html)

* `wind_map.py`: データ洗浄、風向ベクトル分解、Foliumマップ生成のメインスクリプト
* `wind_map_master.html`: 生成された wind rosesマップ
* 解析ロジックとデータ処理
風向の16方位を単なる頻度ではなく、三角関数（$\sin^2\theta, \cos^2\theta$）を用いて東西・南北ベクトルにに分解しています。さらにMatplotlibで極座標グラフを生成し、Base64エンコードによりFoliumマップ内に直接埋め込んでいます。
