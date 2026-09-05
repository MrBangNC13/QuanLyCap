import json
import pandas as pd
import networkx as nx
import folium
import streamlit as st
from streamlit_folium import st_folium

# -----------------------------------------------------------------------------
# 1. HÀM ĐỌC DỮ LIỆU JSON TỰ ĐỘNG LẠI TẤT CẢ CÁC ĐỊNH DẠNG (UNIVERSAL PARSER)
# -----------------------------------------------------------------------------
def parse_json_data(data):
    G = nx.Graph()
    node_coords = {}

    if isinstance(data, (str, bytes)):
        data = json.loads(data)

    # Nếu dữ liệu bọc trong 1 dict chính, tìm danh sách phần tử bên trong
    items = []
    if isinstance(data, dict):
        # Kiểm tra chuẩn GeoJSON
        if data.get("type") == "FeatureCollection":
            items = data.get("features", [])
        else:
            # Tìm danh sách bất kỳ trong dict (nodes, links, data, items, cables...)
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 0:
                    items = v
                    break
    elif isinstance(data, list):
        items = data

    # Duyệt qua các phần tử để bóc tách nút, đoạn cáp và tọa độ
    for item in items:
        if not isinstance(item, dict):
            continue

        # Nếu là Feature của GeoJSON
        if item.get("type") == "Feature":
            geom = item.get("geometry", {})
            props = item.get("properties", {})
            geom_type = geom.get("type")
            coords = geom.get("coordinates", [])

            if geom_type == "Point" and len(coords) >= 2:
                node_id = str(props.get("name") or props.get("id") or props.get("code")).strip()
                node_coords[node_id] = (float(coords[1]), float(coords[0]))
                G.add_node(node_id)
            elif geom_type == "LineString" and len(coords) >= 2:
                u = str(props.get("from") or props.get("start") or props.get("source")).strip()
                v = str(props.get("to") or props.get("end") or props.get("target")).strip()
                cable_id = str(props.get("cable_name") or props.get("name") or f"{u}-{v}").strip()
                length = float(props.get("length") or props.get("len") or 0.0)

                if not u or u == "None":
                    u = f"Node_{coords[0][1]}_{coords[0][0]}"
                    node_coords[u] = (float(coords[0][1]), float(coords[0][0]))
                if not v or v == "None":
                    v = f"Node_{coords[-1][1]}_{coords[-1][0]}"
                    node_coords[v] = (float(coords[-1][1]), float(coords[-1][0]))

                G.add_edge(u, v, cable=cable_id, length=length)
            continue

        # Tìm tên 2 điểm kết nối (Duyệt nhiều từ khóa phổ biến)
        u = str(
            item.get("Điểm KN1") or item.get("from") or item.get("source") or 
            item.get("start") or item.get("node1") or item.get("diem1") or ""
        ).strip()
        
        v = str(
            item.get("Điểm KN2") or item.get("to") or item.get("target") or 
            item.get("end") or item.get("node2") or item.get("diem2") or ""
        ).strip()

        # Tìm tên tuyến cáp & chiều dài
        cable_id = str(
            item.get("Tên đoạn cáp") or item.get("cable_name") or 
            item.get("cable") or item.get("name") or item.get("id") or f"{u}-{v}"
        ).strip()
        
        length = float(
            item.get("Chiều dài thực (m)") or item.get("length") or 
            item.get("len") or item.get("distance") or 0.0
        )

        # Lấy tọa độ nếu có
        lat1 = item.get("lat1") or item.get("lat_1") or item.get("latitude1")
        lon1 = item.get("lng1") or item.get("lon_1") or item.get("longitude1")
        lat2 = item.get("lat2") or item.get("lat_2") or item.get("latitude2")
        lon2 = item.get("lng2") or item.get("lon_2") or item.get("longitude2")

        if lat1 is not None and lon1 is not None and u:
            node_coords[u] = (float(lat1), float(lon1))
        if lat2 is not None and lon2 is not None and v:
            node_coords[v] = (float(lat2), float(lon2))

        if u and v:
            G.add_edge(u, v, cable=cable_id, length=length)

    return G, node_coords, data

# -----------------------------------------------------------------------------
# 2. GIAO DIỆN STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Xác định vị trí đứt cáp", layout="wide")

st.title("⚡ XÁC ĐỊNH VỊ TRÍ ĐỨT CÁP")
st.caption("Fiber Optic Break Location Finder")

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
# 3. XỬ LÝ DỮ LIỆU VÀ TRUY XUẤT CẤU TRÚC
# -----------------------------------------------------------------------------
if uploaded_file is not None:
    try:
        G = nx.Graph()
        node_coords = {}
        raw_json_data = None

        if file_type == "File JSON (.json)":
            content = uploaded_file.read()
            raw_json_data = json.loads(content.decode("utf-8"))
            G, node_coords, raw_json_data = parse_json_data(raw_json_data)

        else:
            df = pd.read_excel(uploaded_file)
            for _, row in df.iterrows():
                u = str(row.get("Điểm KN1", "")).strip()
                v = str(row.get("Điểm KN2", "")).strip()
                cable = str(row.get("Tên đoạn cáp", f"{u}-{v}")).strip()
                length = float(row.get("Chiều dài thực (m)", 0.0))
                if u and v:
                    G.add_edge(u, v, cable=cable, length=length)

        # Hiển thị kết quả đọc
        if len(G.nodes) > 0:
            st.success(f"✅ Đã tải dữ liệu thành công! Tổng số Nút: **{len(G.nodes)}** | Số Đoạn cáp: **{len(G.edges)}**")
            
            if node_coords:
                avg_lat = sum(lat for lat, lon in node_coords.values()) / len(node_coords)
                avg_lon = sum(lon for lat, lon in node_coords.values()) / len(node_coords)
                
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)

                for u, v, data in G.edges(data=True):
                    if u in node_coords and v in node_coords:
                        folium.PolyLine(
                            locations=[node_coords[u], node_coords[v]],
                            color="blue",
                            weight=4,
                            opacity=0.7,
                            popup=f"Cáp: {data.get('cable', 'N/A')} ({data.get('length', 0)}m)"
                        ).add_to(m)

                for node_id, coord in node_coords.items():
                    folium.Marker(
                        location=coord,
                        popup=f"Nút: {node_id}",
                        icon=folium.Icon(color="red", icon="info-sign")
                    ).add_to(m)

                st_folium(m, width="100%", height=550)
            else:
                st.info("ℹ️ Đã nạp danh sách các tuyến cáp thành công (không có tọa độ GPS).")

        else:
            st.warning("⚠️ Đã tải file lên nhưng chưa nhận diện đúng cấu trúc trường (keys).")
            
            # Khung soi cấu trúc File JSON giúp khắc phục nhanh
            if raw_json_data is not None:
                with st.expander("🔍 Bấm vào đây để xem cấu trúc mẫu của file TQGP001.json"):
                    st.write("Dưới đây là một phần dữ liệu thực tế từ file của bạn:")
                    if isinstance(raw_json_data, list) and len(raw_json_data) > 0:
                        st.json(raw_json_data[0])
                    elif isinstance(raw_json_data, dict):
                        st.json({k: raw_json_data[k] for k in list(raw_json_data.keys())[:3]})

    except Exception as e:
        st.error(f"❌ Có lỗi xảy ra khi xử lý file: {str(e)}")

else:
    st.info("👉 Vui lòng tải file Excel hoặc JSON lên ở thanh bên trái để xem dữ liệu.")
