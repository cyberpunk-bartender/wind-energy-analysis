import os
import re
import pandas as pd
import folium
import sqlite3
import numpy as np
import matplotlib.pyplot as plt
import io
import base64

print("⏳ 正在读取站点坐标与数据库...")

# 1. 兼容性读取字典
try:
    df_dict = pd.read_csv('station_dict.csv', names=['name', 'id', 'h0', 'region', 'lat', 'lon'], encoding='utf-8')
except UnicodeDecodeError:
    df_dict = pd.read_csv('station_dict.csv', names=['name', 'id', 'h0', 'region', 'lat', 'lon'], encoding='shift_jis')

# 去除 ID 的首尾空格
df_dict['id'] = df_dict['id'].astype(str).str.strip()

# 2. 从数据库提取【白名单站点】的风速和风向
conn = sqlite3.connect('wind_project.db')
query = "SELECT station_id, wind_dir, wind_0m FROM wind_data WHERE wind_dir != 'UNKNOWN' AND wind_dir IS NOT NULL"
df_wind = pd.read_sql_query(query, conn)
conn.close()

# 建立风向到角度的精确映射（正北为0度，顺时针）
dir_angles = {
    'N': 0, 'NNE': 22.5, 'NE': 45, 'ENE': 67.5,
    'E': 90, 'ESE': 112.5, 'SE': 135, 'SSE': 157.5,
    'S': 180, 'SSW': 202.5, 'SW': 225, 'WSW': 247.5,
    'W': 270, 'WNW': 292.5, 'NW': 315, 'NNW': 337.5
}
# === 💡 新增：建立站点ID到颜色的映射字典 ===
color_map = {}
for _, row in df_dict.iterrows():
    reg = row['region']
    if reg == 'hokkaido': color_map[str(row['id']).strip()] = '#3186cc'  # 蓝
    elif reg == 'tohoku': color_map[str(row['id']).strip()] = '#2ca02c'  # 绿
    else: color_map[str(row['id']).strip()] = '#d62728'                  # 红
def calculate_station_stats(df_subset):
    if len(df_subset) == 0: 
        return pd.Series({'N':0, 'S':0, 'E':0, 'W':0, 'avg_speed':0, 'wind_rose_img': ""})
    
    n_w, s_w, e_w, w_w = 0, 0, 0, 0
    valid_winds = 0
    
    # 记录16方位的频次，用于画玫瑰图
    rose_counts = {k: 0 for k in dir_angles.keys()}

    # 1. 遍历计算每个风向的三角函数权重
    for wd in df_subset['wind_dir'].astype(str).str.upper():
        if wd in dir_angles:
            angle = dir_angles[wd]
            rad = np.radians(angle)
            
            # 使用平方保证权重之和为 1
            cos_sq = np.cos(rad)**2
            sin_sq = np.sin(rad)**2
            
            if np.cos(rad) > 0: n_w += cos_sq
            else: s_w += cos_sq
                
            if np.sin(rad) > 0: e_w += sin_sq
            else: w_w += sin_sq
                
            valid_winds += 1
            rose_counts[wd] += 1

    if valid_winds == 0:
        return pd.Series({'N':0, 'S':0, 'E':0, 'W':0, 'avg_speed':0, 'wind_rose_img': ""})

    # 2. 生成风向玫瑰图 (Matplotlib 极坐标)
    # 💡 新增：获取当前站点的ID，并查表得到对应颜色
    st_id = str(df_subset.name).strip()
    rose_color = color_map.get(st_id, '#3186cc') # 默认给蓝色

    fig, ax = plt.subplots(figsize=(2.5, 2.5), subplot_kw=dict(polar=True))
    angles = [np.radians(dir_angles[d]) for d in rose_counts.keys()]
    counts = list(rose_counts.values())
    
    # 💡 修改：将写死的颜色替换为 rose_color 变量
    ax.bar(angles, counts, width=0.3, color=rose_color, alpha=0.7, edgecolor='black')
    ax.set_theta_zero_location('N') # 北方在正上
    ax.set_theta_direction(-1)      # 顺时针
    ax.set_xticks(np.radians([0, 45, 90, 135, 180, 225, 270, 315]))
    ax.set_xticklabels(['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'], fontsize=8)
    ax.set_yticks([]) # 隐藏内部的同心圆标尺以节省空间
    plt.tight_layout()

    # 3. 将图片转为 Base64 字符串
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', transparent=True)
    plt.close(fig) # 极其重要：释放内存
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return pd.Series({
        'N': (n_w / valid_winds) * 100,
        'S': (s_w / valid_winds) * 100,
        'E': (e_w / valid_winds) * 100,
        'W': (w_w / valid_winds) * 100,
        'avg_speed': df_subset['wind_0m'].mean(),
        'wind_rose_img': img_base64
    })

print("⚙️ 正在通过三角函数计算权重，并绘制风向玫瑰图...")
df_stats = df_wind.groupby('station_id').apply(calculate_station_stats)

# 💡 修复点：合并数据 & 补全正则
df_merged = df_dict.merge(df_stats, left_on='id', right_index=True, how='left')
wind_pattern = re.compile(r'\b(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW|C|CALM)\s*(\d{1,3})\b', re.IGNORECASE)

# 4. 绘图准备
m = folium.Map(location=[38.0, 140.0], zoom_start=6)

print("🎨 正在生成终极分布地图...")
for _, row in df_merged.iterrows():
    st_id = str(row['id']).strip()
    if pd.isna(row['lat']) or pd.isna(row['lon']): continue
    
    is_valid = pd.notna(row['avg_speed'])
    
    if is_valid:
        # ================================
        # ✅ 白名单站点：详细报告 + 彩色实心圆
        # ================================
        popup_text = f"""
        <div style='width: 200px; font-family: Arial;'>
            <b style='font-size: 14px;'>{row['name']}</b> ({st_id})<br>
            <span style='color: #d9534f; font-weight: bold;'>有效风速: {row['avg_speed']:.2f} m/s</span>
            <hr style='margin: 5px 0;'>
            <!-- 插入生成的 Base64 风向玫瑰图 -->
            <img src="data:image/png;base64,{row['wind_rose_img']}" width="100%">
            <hr style='margin: 5px 0;'>
            <div style='font-size: 12px;'>
                <b>风向分解权重 (总和 100%):</b><br>
                N: {row['N']:.1f}% | S: {row['S']:.1f}%<br>
                E: {row['E']:.1f}% | W: {row['W']:.1f}%
            </div>
        </div>
        """
        if row['region'] == 'hokkaido': color = '#3186cc'  
        elif row['region'] == 'tohoku': color = '#2ca02c'  
        else: color = '#d62728'  
        
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=8,
            popup=folium.Popup(popup_text, max_width=200),
            color=color, fill=True, fill_color=color, fill_opacity=0.7
        ).add_to(m)

    else:
        # ================================
        # ❌ 淘汰站点：现场算风速 + 灰色空心圆
        # ================================
        total_speed = 0.0
        valid_count = 0
        for y in range(2019, 2025):
            filepath = os.path.join(st_id, f"{st_id}_{y}.dat")
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='shift_jis', errors='ignore') as f:
                    for line in f:
                        match = wind_pattern.search(line)
                        if match:
                            total_speed += float(match.group(2)) / 10.0
                            valid_count += 1
                            
        invalid_avg_speed = (total_speed / valid_count) if valid_count > 0 else 0.0
        
        if invalid_avg_speed > 0:
            popup_text = f"""
            <div style='width: 160px; font-family: Arial;'>
                <b style='font-size: 14px; color: #555;'>{row['name']}</b> ({st_id})<br>
                <span style='color: #777; font-size: 12px;'>(不具备经济价值)</span>
                <hr style='margin: 5px 0;'>
                <span style='color: #555; font-weight: bold;'>平均风速: {invalid_avg_speed:.2f} m/s</span><br>
                <span style='color: #d9534f; font-size: 11px;'>*已从并网分析中排除</span>
            </div>
            """
            
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=6, 
                popup=folium.Popup(popup_text, max_width=200),
                color='gray', weight=2, fill=True, fill_color='white', fill_opacity=0.5
            ).add_to(m)

m.save('wind_map_master.html')
print("✅ 终极地图已生成！包含白名单风向与被排除站点的风速标注，快打开看看！")