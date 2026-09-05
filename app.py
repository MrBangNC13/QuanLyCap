import json
import pandas as pd
import networkx as nx
import folium
import streamlit as st
from streamlit_folium import st_folium

# -----------------------------------------------------------------------------
# 1. KHAI BÁO HÀM XỬ LÝ DỮ LIỆU JSON (PARSER)
# -----------------------------------------------------------------------------
def parse_json_data(data):
    """
    Hàm đọc và chuyển đổi dữ liệu JSON thành Đồ thị (NetworkX) 
    và Tọa độ các điểm (node_coords).
    """
    G = nx.Graph()
    node_coords = {}

    # Chuyển đổi nếu dữ liệu đầu vào dạng chuỗi hoặc bytes
    if isinstance(data, (str, bytes)):
        data = json.loads(data)

    # DẠNG 1: JSON chứa danh sách 'nodes' và 'links' / 'edges'
    if isinstance(data, dict) and ("nodes" in data or "links" in data or "edges" in data):
        for node in data.get("nodes", []):
            node_id = str(node.get("id") or node.get("name") or node.get("label")).strip()
            lat = node.get("lat") or node.get("latitude") or node.get("y")
            lon = node.get("lng") or node.get("lon") or node.get("longitude") or node.get("x")
            if lat is not None and lon is not None:
                node_coords[node_id] = (float(lat), float(lon))
                G.add_node(node_id)

        links = data.get("links") or data.get("edges") or []
        for link in links:
            u = str(link.get("from") or link.get("source")).strip()
            v = str(link.get("to") or link.get("target")).strip()
            cable_id = str(link.get("cable_name") or link.get("cable") or link.get("id") or f"{u}-{v}").strip()
            length = float(link.get("length", 0.0))
            if u and v:
                G.add_edge(u, v, cable=cable_id, length=length)

    # DẠNG 2: Định dạng Chuẩn Địa lý GeoJSON (FeatureCollection)
    elif isinstance(data, dict) and data.get("type") == "FeatureCollection":
        for feature in data.get("features", []):
            geom = feature.get("geometry", {})
            geom_type = geom.get("type")
            coords = geom.get("coordinates", [])
            props = feature.get("properties", {})

            if geom_type == "Point" and len(coords) >= 2:
                node_id = str(props.get("name") or props.get("id")).strip()
                lon, lat = coords[0], coords[1]
                node_coords[node_id] = (float(lat), float(lon))
                G.add_node(node_id)

            elif geom_type == "LineString" and len(coords) >= 2:
                u = str(props.get("from") or props.get("source")).strip()
                v = str(props.get("to") or props.get("target")).strip()
                cable_id = str(props.get("cable_name") or props.get("name") or f"{u}-{v}").strip()
                length = float(props.get("length", 0.0))
                
                # Nếu không có tên nút u, v sẵn trong properties, lấy tọa độ đầu-cuối
                if not u or u == "None":
                    u = f"Node_{coords[0][1]}_{coords[0][0]}"
                    node_coords[u] = (float(coords[0][1]), float(coords[0][0]))
                if not v or v == "None":
                    v = f"Node_{coords[-1][1]}_{coords[-1][0]}"
                    node_coords[v] = (float(coords[-1][1]), float(coords[-1][0]))

                G.add_edge(u, v, cable=cable_id, length=length)

    # DẠNG 3: JSON dạng Danh sách đối tượng (List of Dicts)
    elif isinstance(data, list):
        for item in data:
            u = str(item.get("Điểm KN1") or item.get("from") or item.get("source")).strip()
            v = str(item.get("Điểm KN2") or item.get("to") or item.get("target")).strip()
            cable_id = str(item.get("Tên đoạn cáp") or item.get("cable_name") or f"{u}-{v}").strip()
            length = float(item.get("Chiều dài thực (m)") or item.get("length", 0.0))

            lat1 = item.get("lat1") or item.get("lat_1")
            lon1 = item.get("lng1") or item.get("lon_1")
            lat2 = item.get("lat2") or item.get("lat_2")
            lon2 = item.get("lon2") or item.get("lon_2")

            if lat1 is not None and lon1 is not None and u:
                node_coords[u] = (float(lat1), float(lon1))
            if lat2 is not None and lon2 is not None and v:
                node_coords[v] = (float(lat2), float(lon2))

            if u and v:
                G.add_edge(u, v, cable=cable_id, length=length)

    return G, node_coords


# -----------------------------------------------------------------------------
# 2. GIAO DIỆN STREAMLIT (UI & SIDEBAR)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Xác định vị trí đứt cáp", layout="wide")

st.title("⚡ XÁC ĐỊNH VỊ TRÍ ĐỨT CÁP")
st.caption("Fiber Optic Break Location Finder")

# Sidebar Quản lý dữ liệu
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
# 3. XỬ LÝ UPLOAD FILE & HIỂN THỊ BẢN ĐỒ
# -----------------------------------------------------------------------------
if uploaded_file is not None:
    try:
        G = nx.Graph()
        node_coords = {}

        # Trường hợp 1: File JSON
        if file_type == "File JSON (.json)":
            content = uploaded_file.read()
            json_data = json.loads(content.decode("utf-8"))
            G, node_coords = parse_json_data(json_data)

        # Trường hợp 2: File Excel
        else:
            df = pd.read_excel(uploaded_file)
            for _, row in df.iterrows():
                u = str(row.get("Điểm KN1", "")).strip()
                v = str(row.get("Điểm KN2", "")).strip()
                cable = str(row.get("Tên đoạn cáp", f"{u}-{v}")).strip()
                length = float(row.get("Chiều dài thực (m)", 0.0))
                if u and v:
                    G.add_edge(u, v, cable=cable, length=length)

        # Kiểm tra xem Đồ thị có dữ liệu hay không
        if len(G.nodes) > 0:
            st.success(f"✅ Đã tải dữ liệu thành công! Tổng số Nút (Trạm): **{len(G.nodes)}** | Số Đoạn cáp: **{len(G.edges)}**")
            
            # --- HIỂN THỊ BẢN ĐỒ FOLIUM ---
            if node_coords:
                # Lấy tọa độ trung bình làm tâm bản đồ
                avg_lat = sum(lat for lat, lon in node_coords.values()) / len(node_coords)
                avg_lon = sum(lon for lat, lon in node_coords.values()) / len(node_coords)
                
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)

                # Vẽ các tuyến cáp (Edges)
                for u, v, data in G.edges(data=True):
                    if u in node_coords and v in node_coords:
                        coord_u = node_coords[u]
                        coord_v = node_coords[v]
                        folium.PolyLine(
                            locations=[coord_u, coord_v],
                            color="blue",
                            weight=4,
                            opacity=0.7,
                            popup=f"Cáp: {data.get('cable', 'N/A')} ({data.get('length', 0)}m)"
                        ).add_to(m)

                # Vẽ các điểm/trạm (Nodes)
                for node_id, coord in node_coords.items():
                    folium.Marker(
                        location=coord,
                        popup=f"Nút: {node_id}",
                        icon=folium.Icon(color="red", icon="info-sign")
                    ).add_to(m)

                # Render bản đồ ra màn hình Streamlit
                st_folium(m, width="100%", height=550)
            else:
                st.info("ℹ️ Đã nạp danh sách các tuyến cáp thành công (không có dữ liệu tọa độ GPS để vẽ bản đồ).")

        else:
            st.warning("⚠️ Đã tải file lên nhưng không đọc được dữ liệu nút/cáp hợp lệ. Vui lòng kiểm tra lại cấu trúc file!")

    except Exception as e:
        st.error(f"❌ Có lỗi xảy ra khi xử lý file: {str(e)}")

else:
    st.info("👉 Vui lòng tải file Excel hoặc JSON lên ở thanh bên trái để xem dữ liệu.")
