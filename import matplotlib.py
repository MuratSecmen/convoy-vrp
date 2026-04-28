import matplotlib.pyplot as plt

# Veriler
points = [1, 2, 3, 4, 5]
L1 = [350.33, 289.19, 289.84, 281.37, 263.4]
L2 = [323.52, 326.54, 323.52, 323.52, 314.45]
L3 = [363.4, 363.4, 363.4, 363.4, 363.4]
W2 = [1.0, 0.754639, 0.509277, 0.263916, 0.018555]

# Grafiği Oluşturma
plt.figure(figsize=(10, 6))

# Çizgiler (L1, L2, L3)
plt.plot(points, L1, marker='o', label='L_1', color='blue')
plt.plot(points, L2, marker='s', label='L_2', color='green')
plt.plot(points, L3, marker='^', label='L_3', color='red', linestyle='--')

# Knee (Kırılma) noktasını işaretleme (Sadece Point 1'de)
plt.scatter([1], [350.33], color='gold', s=200, label='Knee (Nokta 1)', zorder=5, edgecolors='black')

# Etiketler ve Başlık
plt.title('Noktalara Göre L_1, L_2 ve L_3 Değerlerinin Değişimi')
plt.xlabel('Nokta (Point)')
plt.ylabel('Değerler')
plt.xticks(points)
plt.legend()
plt.grid(True, linestyle=':', alpha=0.7)

# Grafiği Göster
plt.show()