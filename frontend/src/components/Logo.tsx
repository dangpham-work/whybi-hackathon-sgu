import logo from "../assets/logo-whybi.svg";

/** Logo/Whybi – chú ong tò mò (Figma component 11:254). */
export function Logo({ size = 32 }: { size?: number }) {
  return <img src={logo} width={size} height={size} alt="Whybi" />;
}
