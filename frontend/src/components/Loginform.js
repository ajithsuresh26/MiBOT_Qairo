import { useState, useEffect } from 'react';
import { useNavigate } from "react-router-dom";


const Login = () => {

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const navigate = useNavigate();
    const images = ['login.png', 'login3.png', 'loginss.png'];
    const [index, setIndex] = useState(0);
    const [showPassword, setShowPassword] = useState(false);

    const handleLogin = async (e) => {
        e.preventDefault();

        try {
            const res = await fetch('http://127.0.0.1:5000/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email,
                    password,
                }),
            });

            const data = await res.json();
            console.log(data);
            
            if (data.success === true) {
                alert("Login successful!");
                navigate("/home");
            } else {
                alert(data.msg || "Invalid email or password");
            }
        } catch (error) {
            console.error("Login error:", error);
        }
    };


    useEffect(() => {
        const interval = setInterval(() => {
            setIndex((prev) => (prev + 1) % images.length);
        }, 3000);

        return () => clearInterval(interval);
    }, [images.length]);

    return (
        <div className="relative min-h-screen flex items-center justify-end pr-20  bg-cover bg-center" style={{ backgroundImage: 'url("/bg.png")' }}>
            {/* Overlay */}
            <img
                alt="login"
                src={images[index]}
                className="h-[700px] w-[700px] object-contain transition-opacity duration-500 ease-in-out"
            />

            {/* Login Card */}
            <div className="relative z-10 bg-white  shadow-xl rounded-xl p-8 w-[90%] max-w-md bg-opacity-90">
                <h2 className="text-2xl font-bold text-center mb-4">Login</h2>
                <p className="text-sm text-gray-600 text-center mb-6">
                    Welcome! Please enter your details & Join with us
                </p>

                <form onSubmit={handleLogin}>
                    <div className="mb-4">
                        <label className="block text-sm mb-1 font-medium text-gray-700 ">User ID</label>
                        <input
                            type="email"
                            placeholder="Enter your email"
                            className="w-full px-4 py-2 border border-black rounded "
                            onChange={(e) => setEmail(e.target.value)}
                            value={email}
                            required
                        />
                    </div>

                    <div className="mb-6 relative">
                    <label className="block text-sm mb-1 font-medium text-gray-700">Password</label>
                        <input
                            type={showPassword ? "text" : "password"}
                            placeholder="**********"
                            className="w-full px-4 py-2 border border-black rounded pr-10"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                        />
                        <span
                            onClick={() => setShowPassword((prev) => !prev)}
                            className="absolute right-3 top-9 cursor-pointer"
                            title={showPassword ? "Hide password" : "Show password"}
                        >
                            <img
                                src={showPassword ? "/eye-closed.png" : "/eye-open.png"}
                                alt={showPassword ? "Hide" : "Show"}
                                className="w-5 h-5"
                            />
                        </span>
                    </div>

                    <button
                        type="submit"
                        className="w-1/2 bg-blue-900 text-white text-center font-semibold py-2 rounded-full mx-auto block"
                    >
                        Login
                    </button>

                </form>

                <p className="mt-4 text-xs text-gray-700 text-center">
                    Please enter your valid mail id. If any issue contact your admin
                </p>
            </div>
        </div>
    );
};

export default Login;
