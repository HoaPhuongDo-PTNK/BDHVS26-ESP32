import tkinter as tk
import serial
import time

khoang_chua = {"Titanium": 0, "Uranium": 0}
ban_do_radar = ["Titanium", "Dat_da", "Thien_thach", "Uranium", "Thien_thach", "Ho_den", "Titanium"]

try:
    esp = serial.Serial('COM13  ', 9600, timeout=1)
    time.sleep(2)
    print("Kết nối ESP thành công!")
except Exception as e:
    print("Kiểm tra lại cáp hoặc cổng COM, Chi tiết:", e)
    esp = None

def phan_tich_radar(vat_the):
    """
    Hàm phân tích vật thể từ dữ liệu Radar và ra quyết định hành động.
    """
    global esp
    
    if vat_the == "Titanium" or vat_the == "Uranium":
        khoang_chua[vat_the] += 1
        if esp is not None:
            esp.write(b'1')
        return "KHOANG_SAN"
        
    elif vat_the == "Dat_da":
        print("Bỏ qua đất đá")
        return "DAT_DA"
        
    elif vat_the == "Thien_thach":
        if esp is not None:
            esp.write(b'0')
        return "THIEN_THACH"
        
    elif vat_the == "Ho_den":
        return "HO_DEN"
        
    else:
        return "KHONG_XAC_DINH"

def khoi_dong_he_thong_quet():
    khoang_chua["Titanium"] = 0
    khoang_chua["Uranium"] = 0
    cap_nhat_giao_dien_khoang_san()
    
    for index, vat_the in enumerate(ban_do_radar):
        nhan_trang_thai.config(text=f"ĐANG QUÉT VẬT THỂ MỤC TIÊU {index+1}/{len(ban_do_radar)}...", fg="#e67e22")
        nhan_vat_the.config(text=f"Vật thể hiện tại: {vat_the}", fg="#34495e")
        cua_so.update()
        time.sleep(1.5)
        
        ket_qua = phan_tich_radar(vat_the)
        
        if ket_qua == "KHOANG_SAN":
            nhan_trang_thai.config(text=f"Đã thu thập {vat_the}!", fg="#27ae60")
            cap_nhat_giao_dien_khoang_san()
            
        elif ket_qua == "DAT_DA":
            nhan_trang_thai.config(text="Bỏ qua đất đá", fg="#7f8c8d")
            
        elif ket_qua == "THIEN_THACH":
            nhan_trang_thai.config(text="Kích hoạt Laser phá hủy Thiên Thạch", fg="#c0392b")
            
        elif ket_qua == "HO_DEN":
            nhan_trang_thai.config(text="PHANH KHẨN CẤP! GẶP HỐ ĐEN VU TRỤ", fg="#8e44ad")
            nhan_an_toan.config(text="DỪNG KHẨN CẤP", fg="#8e44ad")
            cua_so.update()
            break
            
        cua_so.update()
        time.sleep(1)
        
    else:
        nhan_trang_thai.config(text="Đã quét hết bản đồ radar an toàn", fg="#2ecc71")
        nhan_an_toan.config(text="Robot an toàn", fg="#2ecc71")

def cap_nhat_giao_dien_khoang_san():
    """Hàm phụ trợ cập nhật số lượng khoáng sản lên màn hình Dashboard"""
    nhan_titanium.config(text=f"Titanium: {khoang_chua['Titanium']} đơn vị")
    nhan_uranium.config(text=f"Uranium: {khoang_chua['Uranium']} đơn vị")

cua_so = tk.Tk()
cua_so.title("HỆ THỐNG ĐIỀU KHIỂN ROBOT VŨ TRỤ")
cua_so.geometry("450x420")
cua_so.config(bg="#f5f6fa")

tieu_de = tk.Label(cua_so, text="ROBOTIC CONTROL DASHBOARD", font=("Arial", 14, "bold"), bg="#2c3e50", fg="white", pady=10)
tieu_de.pack(fill="x")

khung_khoang_san = tk.LabelFrame(cua_so, text=" KHOANG CHỨA PHI THUYỀN ", font=("Arial", 10, "bold"), padx=10, pady=10, bg="#ffffff")
khung_khoang_san.pack(pady=15, padx=20, fill="x")

nhan_titanium = tk.Label(khung_khoang_san, text="Titanium: 0 đơn vị", font=("Arial", 11), bg="#ffffff", fg="#2c3e50")
nhan_titanium.pack(anchor="w", pady=2)

nhan_uranium = tk.Label(khung_khoang_san, text="Uranium: 0 đơn vị", font=("Arial", 11), bg="#ffffff", fg="#2c3e50")
nhan_uranium.pack(anchor="w", pady=2)

khung_trang_thai = tk.LabelFrame(cua_so, text=" TRẠNG THÁI & HỆ THỐNG ", font=("Arial", 10, "bold"), padx=10, pady=10, bg="#ffffff")
khung_trang_thai.pack(pady=10, padx=20, fill="x")

nhan_vat_the = tk.Label(khung_trang_thai, text="Vật thể hiện tại: Chưa quét", font=("Arial", 10, "italic"), bg="#ffffff", fg="#7f8c8d")
nhan_vat_the.pack(anchor="w")

nhan_trang_thai = tk.Label(khung_trang_thai, text="Hệ thống đang chờ lệnh từ Chỉ huy...", font=("Arial", 11, "bold"), bg="#ffffff", fg="#34495e")
nhan_trang_thai.pack(anchor="w", pady=5)

nhan_an_toan = tk.Label(khung_trang_thai, text="SẴN SÀNG KHỞI HÀNH", font=("Arial", 10, "bold"), bg="#ffffff", fg="#2ecc71")
nhan_an_toan.pack(anchor="w")

nut_quet = tk.Button(cua_so, text="KHỞI ĐỘNG HỆ THỐNG QUÉT", font=("Arial", 12, "bold"), bg="#0984e3", fg="white", activebackground="#74b9ff", activeforeground="white", bd=3, pady=8, command=khoi_dong_he_thong_quet)
nut_quet.pack(pady=20, padx=20, fill="x")

cua_so.mainloop()