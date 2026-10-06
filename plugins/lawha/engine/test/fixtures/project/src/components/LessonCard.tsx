type Props = { title: string; minutes?: number; status: "planned" | "reviewed" };
export function LessonCard({ title }: Props) {
  return <div className="ml-4 p-[13px] text-[#ff0000]">{title}</div>;
}
export const Badge = ({ label }: { label: string }) => <span>{label}</span>;
