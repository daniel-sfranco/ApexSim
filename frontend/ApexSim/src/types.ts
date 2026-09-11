export type Circuit = {
    circuitId: string;
    lengthM: number;
    points: Points[];
}

export type Points = {
    x: number;
    y: number;
    distanceM: number;
}