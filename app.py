import json
import re
import pandas as pd
import networkx as nx
import folium
import streamlit as st
from streamlit_folium import st_folium

# -----------------------------------------------------------------------------
# 1. HÀM GIẢI MÃ VÀ BÓC TÁCH FILE JSON ĐA LỚP
# -----------------------------------------------------------------------------
def parse_json_data(data):
    G = nx.Graph()
    node_coords = {}

    if isinstance(data, (str, bytes)):
        data = json.loads(data)

    # Giải mã lớp 1: 'results'
    if isinstance(data, dict) and "results" in data:
        data = data["results"]

    # Giải mã lớp 2: Chuỗi JSON trong 'results'
    if isinstance(data, str):
        try:
            data = json.loads(data.strip())
        except Exception:
            pass

    # Giải mã lớp 3: 'Table'
    if isinstance(data, dict) and "Table" in data:
        table_content = data["Table"]
        if isinstance(table_content, str):
            try:
                table_content = json.loads(table_content)
            except Exception:
                pass
        data = table_content

    # Giải mã lớp 4: 'responseResult'
    if isinstance(data, dict) and "responseResult" in data:
        data = data["responseResult"]

    # Lấy danh sách đối tượng 'objectInfo'
    object_list = []
    if isinstance(data, dict):
        object_list = data.get("result", {}).get("objectInfo", []) or data.get("objectInfo", [])
    elif isinstance(data, list):
        object_list = data

    # Trích xuất Trạm/Nút và Tọa độ latLng dạng "(lat, lng)"
    for item in object_list:
        if not isinstance(item, dict):
            continue

        node_id = str(item.get("name") or item.get("id") or "").strip()
        lat_lng_str = str(item.get("latLng", "")).strip()

        if lat_lng_str and node_id:
            # Tách số thực từ chuỗi dạng "(21.7992374,105.2110277)"
            coords = re.findall(r"[-+]?\d*\.\d+|\d+", lat_lng_str)
            if len(coords) >= 2:
                lat = float(coords[0])
                lng = float(coords[1])
                node_coords[node_id] = (lat, lng)
                G.add_node(node_id, **item)

    # Tự động tạo tuyến liên kết nối tiếp giữa các trạm kề nhau theo tên
    sorted_nodes = sorted(list(G.nodes()))
    for i in range(len(sorted_nodes) - 1):
        u = sorted_nodes[i]
        v = sorted_nodes[i + 1]
        G.add_edge(u, v, cable=f"Tuyến {u} - {v}", length=0.0)

    return G, node_coords


# -----------------------------------------------------------------------------
# 2. GIAO DIỆN STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Xác định vị trí đứt cáp", layout="wide")

st.title("⚡ XÁC ĐỊNH VỊ TRÍ ĐỨT CÁP")
st.caption("Fiber Optic Break Location Finder")

# Sidebar tải file
st.sidebar.title("📁 QUẢN LÝ DỮ LIỆU")
file_type = st.sidebar.radio(
    "Chọn định dạng dữ liệu:", 
    ("File Excel (.xlsx)", "File JSON (.json)")
)

uploaded_file = None
if file_type == "File JSON (.json)":
    uploaded_file = st.sidebar.file_uploader("Tải lên file JSON", type=["json"])
else:
    uploaded_file = st.sidebar.file_uploader("Tải lên file Excel", type=["xlsx", "xls"])


# -----------------------------------------------------------------------------
# 3. XỬ LÝ UPLOAD VÀ HIỂN THỊ BẢN ĐỒ
# -----------------------------------------------------------------------------
if uploaded_file is not None:
    try:
        G = nx.Graph()
        node_coords = {}

        if file_type == "File JSON (.json)":
            content = uploaded_file.read()
            raw_json_data = json.loads(content.decode("utf-8"))
            G, node_coords = parse_json_data(raw_json_data)

        else:
            df = pd.read_excel(uploaded_file)
            for _, row in df.iterrows():
                u = str(row.get("Điểm KN1", "")).strip()
                v = str(row.get("Điểm KN2", "")).strip()
                cable = str(row.get("Tên đoạn cáp", f"{u}-{v}")).strip()
                length = float(row.get("Chiều dài thực (m)", 0.0))
                if u and v:
                    G.add_edge(u, v, cable=cable, length=length)

        # Hiển thị kết quả lên giao diện
        if len(G.nodes) > 0:
            st.success(f"✅ Đã tải dữ liệu thành công! Tìm thấy **{len(G.nodes)}** Trạm/Nút và **{len(G.edges)}** Đoạn tuyến liên kết.")

            if node_coords:
                # Tính tọa độ trung tâm bản đồ
                avg_lat = sum(lat for lat, lon in node_coords.values()) / len(node_coords)
                avg_lon = sum(lon for lat, lon in node_coords.values()) / len(node_coords)

                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=14)

                # Vẽ tuyến đường kết nối giữa các trạm
                for u, v, data in G.edges(data=True):
                    if u in node_coords and v in node_coords:
                        folium.PolyLine(
                            locations=[node_coords[u], node_coords[v]],
                            color="blue",
                            weight=4,
                            opacity=0.7,
                            popup=f"Tuyến cáp: {data.get('cable', 'N/A')}"
                        ).add_to(m)

                # Vẽ Marker cho từng Trạm/Nút
                for node_id, coord in node_coords.items():
                    folium.Marker(
                        location=coord,
                        popup=f"Trạm/Nút: {node_id}",
                        tooltip=node_id,
                        icon=folium.Icon(color="red", icon="info-sign")
                    ).add_to(m)

                # Render bản đồ lên Streamlit
                st_folium(m, width="100%", height=600)
            else:
                st.info("ℹ️ Đã nạp thành công danh sách trạm nhưng không tìm thấy tọa độ GPS.")

        else:
            st.warning("⚠️ Đã tải file lên nhưng không đọc được dữ liệu. Vui lòng kiểm tra lại file!")

    except Exception as e:
        st.error(f"❌ Có lỗi xảy ra khi đọc file: {str(e)}")

else:
    st.info("👉 Vui lòng tải file Excel hoặc JSON lên ở thanh bên trái để xem dữ liệu.")
