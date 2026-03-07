import type { OptimizationResult } from "@/types";

export const MOCK_RESULT: OptimizationResult = {
  depot: { lat: 50.4501, lng: 30.5234 },
  stats: {
    totalDeliveries: 12,
    totalDriveMin: 187,
    totalDistanceKm: 62.4,
    numCouriers: 3,
  },
  routes: [
    {
      courierId: 1,
      totalDriveMin: 68,
      totalDistanceKm: 22.1,
      stops: [
        {
          address: "вул. Хрещатик, 1, Київ",
          eta: "09:14",
          driveMin: 12,
          waitMin: 0,
          lat: 50.4481,
          lng: 30.5238,
        },
        {
          address: "вул. Лесі Українки, 10, Київ",
          eta: "09:35",
          driveMin: 18,
          waitMin: 3,
          lat: 50.4411,
          lng: 30.5268,
        },
        {
          address: "вул. Саксаганського, 44, Київ",
          eta: "10:02",
          driveMin: 24,
          waitMin: 0,
          lat: 50.4388,
          lng: 30.5071,
        },
        {
          address: "просп. Перемоги, 26, Київ",
          eta: "10:28",
          driveMin: 14,
          waitMin: 0,
          lat: 50.4556,
          lng: 30.4897,
        },
      ],
    },
    {
      courierId: 2,
      totalDriveMin: 72,
      totalDistanceKm: 24.8,
      stops: [
        {
          address: "вул. Велика Васильківська, 57, Київ",
          eta: "09:18",
          driveMin: 16,
          waitMin: 2,
          lat: 50.4262,
          lng: 30.5197,
        },
        {
          address: "вул. Антоновича, 33, Київ",
          eta: "09:44",
          driveMin: 23,
          waitMin: 0,
          lat: 50.4228,
          lng: 30.5148,
        },
        {
          address: "вул. Дмитрівська, 17, Київ",
          eta: "10:11",
          driveMin: 20,
          waitMin: 0,
          lat: 50.4508,
          lng: 30.5019,
        },
        {
          address: "вул. Артема, 52, Київ",
          eta: "10:36",
          driveMin: 13,
          waitMin: 1,
          lat: 50.4601,
          lng: 30.5143,
        },
      ],
    },
    {
      courierId: 3,
      totalDriveMin: 47,
      totalDistanceKm: 15.5,
      stops: [
        {
          address: "вул. Михайлівська, 8, Київ",
          eta: "09:11",
          driveMin: 9,
          waitMin: 0,
          lat: 50.454,
          lng: 30.5214,
        },
        {
          address: "вул. Прорізна, 3, Київ",
          eta: "09:28",
          driveMin: 14,
          waitMin: 0,
          lat: 50.4496,
          lng: 30.5221,
        },
        {
          address: "вул. Золотоворітська, 2, Київ",
          eta: "09:50",
          driveMin: 18,
          waitMin: 4,
          lat: 50.4521,
          lng: 30.516,
        },
        {
          address: "вул. Ярославів Вал, 14, Київ",
          eta: "10:15",
          driveMin: 6,
          waitMin: 0,
          lat: 50.4513,
          lng: 30.5131,
        },
      ],
    },
  ],
};

export const PROGRESS_STEPS = [
  { id: "upload", label: "Завантаження даних" },
  { id: "geocode", label: "Геокодування адрес" },
  { id: "matrix", label: "Побудова матриці маршрутів" },
  { id: "optimize", label: "Оптимізація маршрутів" },
  { id: "finalize", label: "Фіналізація результатів" },
] as const;
